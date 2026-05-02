import os
import time
import logging
import json
from datetime import datetime, timedelta, timezone
from logging.handlers import RotatingFileHandler
import sys
import io

# Fix Windows console encoding
if sys.platform == 'win32' and 'pytest' not in sys.modules:
    if hasattr(sys.stdout, 'buffer'):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    if hasattr(sys.stderr, 'buffer'):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

import numpy as np
import joblib
from flask import Flask, request, jsonify, g, send_file
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from config import Config
from models import db, Prediction, ModelPerformance, ApiLog

# ============================================
# INITIALIZATION
# ============================================

app = Flask(__name__)
app.config.from_object(Config)
CORS(app)

# Initialize database
db.init_app(app)

# Initialize rate limiter
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[f"{Config.RATE_LIMIT} per minute"],
    storage_uri="memory://"
)

# Setup logging
if not os.path.exists('logs'):
    os.mkdir('logs')
file_handler = RotatingFileHandler('logs/bank_ews.log', maxBytes=10240, backupCount=10)
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
))
file_handler.setLevel(logging.INFO)
app.logger.addHandler(file_handler)
app.logger.setLevel(logging.INFO)
app.logger.info('Bank EWS API startup')

# ============================================
# LOAD MODELS
# ============================================

class ModelLoader:
    """Singleton pattern for model loading"""
    _instance = None
    _models = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_models()
        return cls._instance
    
    def _load_models(self):
        """Load all models from disk"""
        app.logger.info("Loading models...")
        try:
            self._models['crisis'] = joblib.load(Config.MODEL_CRISIS_PATH)
            self._models['rare'] = joblib.load(Config.MODEL_RARE_PATH)
            self._models['scaler'] = joblib.load(Config.SCALER_PATH)
            self._models['loaded'] = True
            app.logger.info("Models loaded successfully")
        except Exception as e:
            app.logger.error(f"Failed to load models: {e}")
            self._models['loaded'] = False
    
    def get_model(self, model_type='crisis'):
        return self._models.get(model_type)
    
    def get_scaler(self):
        return self._models.get('scaler')
    
    def is_loaded(self):
        return self._models.get('loaded', False)


model_loader = ModelLoader()

# ============================================
# HELPER FUNCTIONS
# ============================================

def identify_risk_factors(features):
    """Identify which thresholds are being breached"""
    risks = []
    
    if features.get('npa_ratio', 0) > 8:
        risks.append(f"High NPA: {features['npa_ratio']:.1f}% > 8%")
    if features.get('crar_total', 100) < 10.5:
        risks.append(f"Low CRAR: {features['crar_total']:.1f}% < 10.5%")
    if features.get('credit_growth', 0) > 20:
        risks.append(f"Rapid credit growth: {features['credit_growth']:.1f}% > 20%")
    if features.get('repo_rate', 0) > 8:
        risks.append(f"High Repo Rate Environment: {features['repo_rate']}%")
        
    if not risks:
        risks.append("All primary risk indicators are within normal limits")
        
    return risks

def validate_features(features):
    """Validate that features are mathematically possible."""
    errors = []
    
    # Percentages
    if 'crar_total' in features and not (0 <= features['crar_total'] <= 200):
        errors.append("crar_total must be between 0 and 200%")
    if 'npa_ratio' in features and not (0 <= features['npa_ratio'] <= 100):
        errors.append("npa_ratio must be between 0 and 100%")
    if 'repo_rate' in features and features['repo_rate'] < 0:
        errors.append("repo_rate cannot be negative")
    if 'credit_growth' in features and features['credit_growth'] < -100:
        errors.append("credit_growth cannot be less than -100%")
        
    # Absolute amounts
    if 'total_provisions' in features and features['total_provisions'] < 0:
        errors.append("total_provisions cannot be negative")
    if 'interest_income' in features and features['interest_income'] < 0:
        errors.append("interest_income cannot be negative")
    if 'interest_expense' in features and features['interest_expense'] < 0:
        errors.append("interest_expense cannot be negative")
    if 'operating_expense' in features and features['operating_expense'] < 0:
        errors.append("operating_expense cannot be negative")
        
    return errors


def get_model_mode(stress_prevalence=None):
    """Determine which model to use based on current stress prevalence"""
    if stress_prevalence is not None:
        return 'rare' if stress_prevalence < Config.STRESS_PREVALENCE_THRESHOLD else 'crisis'
    
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
    recent_preds = Prediction.query.filter(
        Prediction.created_at >= thirty_days_ago,
        Prediction.stress_prediction == True
    ).count()
    
    total_recent = Prediction.query.filter(
        Prediction.created_at >= thirty_days_ago
    ).count()
    
    if total_recent == 0:
        return 'crisis'
    
    stress_rate = recent_preds / total_recent
    return 'rare' if stress_rate < Config.STRESS_PREVALENCE_THRESHOLD else 'crisis'


def log_api_call(endpoint, method, status_code, response_time):
    """Log API call to database"""
    try:
        log = ApiLog(
            endpoint=endpoint,
            method=method,
            status_code=status_code,
            response_time_ms=response_time,
            ip_address=request.remote_addr
        )
        db.session.add(log)
        db.session.commit()
    except Exception as e:
        app.logger.error(f"Failed to log API call: {e}")


# ============================================
# MIDDLEWARE
# ============================================

@app.before_request
def before_request():
    g.start_time = time.time()


@app.after_request
def after_request(response):
    if hasattr(g, 'start_time'):
        elapsed_ms = (time.time() - g.start_time) * 1000
        log_api_call(
            endpoint=request.endpoint or request.path,
            method=request.method,
            status_code=response.status_code,
            response_time=elapsed_ms
        )
    return response


# ============================================
# API ENDPOINTS
# ============================================

@app.route('/')
def root():
    """API root endpoint"""
    return jsonify({
        'service': 'Bank Early Warning System',
        'version': '2.0.0',
        'status': 'operational',
        'models_loaded': model_loader.is_loaded(),
        'endpoints': {
            'predict': '/api/v1/predict',
            'batch_predict': '/api/v1/predict/batch',
            'health': '/api/v1/health',
            'model_info': '/api/v1/model/info',
            'predictions': '/api/v1/predictions',
            'dashboard_stats': '/api/v1/dashboard/stats',
            'dashboard': '/dashboard'
        }
    })


@app.route('/dashboard')
@limiter.exempt
def dashboard():
    """Serve the interactive dashboard"""
    return send_file('dashboard.html')


@app.route('/api/v1/health')
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'models_loaded': model_loader.is_loaded(),
        'database_connected': True,
        'timestamp': datetime.now(timezone.utc).isoformat()
    })


@app.route('/api/v1/model/info')
def model_info():
    """Get model metadata and feature importance"""
    return jsonify({
        'model_version': '2.0.0',
        'algorithm': 'XGBoost',
        'features': Config.FEATURE_COLUMNS,
        'feature_importance': {
            'npa_ratio': 0.385,
            'crar_total': 0.138,
            'credit_growth': 0.097,
            'total_provisions': 0.075,
            'net_profit': 0.068,
            'operating_expense': 0.062,
            'interest_expense': 0.058,
            'interest_income': 0.052,
            'repo_rate': 0.035,
            'inflation': 0.030
        },
        'thresholds': {
            'npa_warning': 8.0,
            'crar_minimum': 10.5,
            'crisis_mode': Config.CRISIS_THRESHOLD,
            'rare_event_mode': Config.RARE_EVENT_THRESHOLD
        },
        'performance': {
            'crisis_recall_2019_2021': 0.925,
            'crisis_precision_2019_2021': 0.77,
            'rare_precision_2023_2025': 0.474,
            'rare_recall_2023_2025': 0.692,
            'auc_roc': 0.893
        }
    })


@app.route('/api/v1/predict', methods=['POST'])
def predict():
    """Predict stress for a single bank"""
    start_time = time.time()
    
    if not model_loader.is_loaded():
        return jsonify({'error': 'Models not loaded'}), 503
    
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No JSON data provided'}), 400
    
    required_fields = ['bank_name', 'year', 'features']
    for field in required_fields:
        if field not in data:
            return jsonify({'error': f'Missing required field: {field}'}), 400
    
    features = data['features']
    missing_features = set(Config.FEATURE_COLUMNS) - set(features.keys())
    if missing_features:
        return jsonify({'error': f'Missing features: {list(missing_features)}'}), 400
        
    validation_errors = validate_features(features)
    if validation_errors:
        return jsonify({'error': 'Input validation failed', 'details': validation_errors}), 422
    
    try:
        stress_prevalence = data.get('stress_prevalence')
        mode = get_model_mode(stress_prevalence)
        
        if mode == 'crisis':
            model = model_loader.get_model('crisis')
            threshold = Config.CRISIS_THRESHOLD
        else:
            model = model_loader.get_model('rare')
            threshold = Config.RARE_EVENT_THRESHOLD
        
        # Prepare features in correct order
        feature_values = [features[col] for col in Config.FEATURE_COLUMNS]
        feature_array = np.array([feature_values])
        
        scaler = model_loader.get_scaler()
        feature_scaled = scaler.transform(feature_array)
        
        probability = float(model.predict_proba(feature_scaled)[0, 1])  # Convert to Python float
        is_stressed = bool(probability >= threshold)  # Convert to Python bool
        
        risk_factors = identify_risk_factors(features)
        
        prediction_time_ms = (time.time() - start_time) * 1000
        
        prediction_record = Prediction(
            bank_name=data['bank_name'],
            year=data['year'],
            crar_total=features.get('crar_total'),
            npa_ratio=features.get('npa_ratio'),
            total_provisions=features.get('total_provisions'),
            net_profit=features.get('net_profit'),
            interest_income=features.get('interest_income'),
            interest_expense=features.get('interest_expense'),
            operating_expense=features.get('operating_expense'),
            credit_growth=features.get('credit_growth'),
            repo_rate=features.get('repo_rate'),
            inflation=features.get('inflation'),
            stress_probability=probability,
            stress_prediction=is_stressed,
            threshold_used=threshold,
            model_version='2.0.0',
            mode_used=mode,
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent', ''),
            prediction_time_ms=prediction_time_ms
        )
        
        db.session.add(prediction_record)
        db.session.commit()
        
        return jsonify({
            'bank_name': data['bank_name'],
            'year': data['year'],
            'stress_probability': probability,
            'stress_prediction': is_stressed,
            'alert': is_stressed,
            'threshold_used': threshold,
            'mode': mode,
            'model_version': '2.0.0',
            'risk_factors': risk_factors,
            'prediction_id': prediction_record.id,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'response_time_ms': round(prediction_time_ms, 2)
        })
        
    except Exception as e:
        app.logger.error(f"Prediction error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/v1/predict/batch', methods=['POST'])
def predict_batch():
    """Predict stress for multiple banks"""
    start_time = time.time()
    
    if not model_loader.is_loaded():
        return jsonify({'error': 'Models not loaded'}), 503
    
    data = request.get_json()
    if not data or 'banks' not in data:
        return jsonify({'error': 'Missing banks array'}), 400
    
    banks = data['banks']
    if len(banks) > Config.MAX_BATCH_SIZE:
        return jsonify({'error': f'Batch size exceeds maximum of {Config.MAX_BATCH_SIZE}'}), 400
    
    predictions = []
    errors = []
    
    # Use dynamic model selection (same as single predict)
    stress_prevalence = data.get('stress_prevalence')
    mode = get_model_mode(stress_prevalence)
    
    if mode == 'crisis':
        model = model_loader.get_model('crisis')
        threshold = Config.CRISIS_THRESHOLD
    else:
        model = model_loader.get_model('rare')
        threshold = Config.RARE_EVENT_THRESHOLD
    
    scaler = model_loader.get_scaler()
    
    for bank in banks:
        try:
            features = bank['features']
            
            # Input validation
            validation_errors = validate_features(features)
            if validation_errors:
                errors.append({
                    'bank_name': bank.get('bank_name', 'Unknown'),
                    'error': 'Input validation failed',
                    'details': validation_errors
                })
                continue
                
            feature_values = [features[col] for col in Config.FEATURE_COLUMNS]
            feature_array = np.array([feature_values])
            
            feature_scaled = scaler.transform(feature_array)
            
            probability = float(model.predict_proba(feature_scaled)[0, 1])
            is_stressed = bool(probability >= threshold)
            
            # Save to database for audit trail
            prediction_record = Prediction(
                bank_name=bank['bank_name'],
                year=bank['year'],
                crar_total=features.get('crar_total'),
                npa_ratio=features.get('npa_ratio'),
                total_provisions=features.get('total_provisions'),
                net_profit=features.get('net_profit'),
                interest_income=features.get('interest_income'),
                interest_expense=features.get('interest_expense'),
                operating_expense=features.get('operating_expense'),
                credit_growth=features.get('credit_growth'),
                repo_rate=features.get('repo_rate'),
                inflation=features.get('inflation'),
                stress_probability=probability,
                stress_prediction=is_stressed,
                threshold_used=threshold,
                model_version='2.0.0',
                mode_used=mode,
                ip_address=request.remote_addr,
                user_agent=request.headers.get('User-Agent', ''),
                prediction_time_ms=0
            )
            db.session.add(prediction_record)
            
            predictions.append({
                'bank_name': bank['bank_name'],
                'year': bank['year'],
                'stress_probability': probability,
                'stress_prediction': is_stressed,
                'risk_factors': identify_risk_factors(features)
            })
        except Exception as e:
            errors.append({
                'bank_name': bank.get('bank_name', 'unknown'),
                'error': str(e)
            })
    
    # Commit all predictions in one batch
    try:
        db.session.commit()
    except Exception as e:
        app.logger.error(f"Failed to save batch predictions: {e}")
        db.session.rollback()
    
    stressed_count = sum(1 for p in predictions if p['stress_prediction'])
    
    return jsonify({
        'predictions': predictions,
        'errors': errors if errors else None,
        'mode': mode,
        'threshold_used': threshold,
        'summary': {
            'total': len(predictions),
            'stressed': stressed_count,
            'healthy': len(predictions) - stressed_count,
            'stressed_percentage': round(stressed_count / len(predictions) * 100, 2) if predictions else 0
        },
        'response_time_ms': round((time.time() - start_time) * 1000, 2)
    })


@app.route('/api/v1/predictions')
def get_predictions():
    """Get historical predictions"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    bank_name = request.args.get('bank_name')
    
    query = Prediction.query
    if bank_name:
        # Sanitize input: strip SQL wildcards and limit length
        bank_name = bank_name.replace('%', '').replace('_', '').strip()[:100]
        if bank_name:
            query = query.filter(Prediction.bank_name.ilike(f'%{bank_name}%'))
    
    paginated = query.order_by(Prediction.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    return jsonify({
        'predictions': [p.to_dict() for p in paginated.items],
        'total': paginated.total,
        'page': page,
        'per_page': per_page,
        'pages': paginated.pages
    })


@app.route('/api/v1/dashboard/stats')
def dashboard_stats():
    """Get dashboard statistics for monitoring"""
    
    seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
    
    recent_predictions = Prediction.query.filter(
        Prediction.created_at >= seven_days_ago
    ).all()
    
    total = len(recent_predictions)
    alerts = sum(1 for p in recent_predictions if p.stress_prediction)
    
    crisis_mode_usage = sum(1 for p in recent_predictions if p.mode_used == 'crisis')
    rare_mode_usage = sum(1 for p in recent_predictions if p.mode_used == 'rare_event')
    
    top_banks = db.session.query(
        Prediction.bank_name, func.count(Prediction.id).label('count')
    ).filter(
        Prediction.created_at >= seven_days_ago,
        Prediction.stress_prediction == True
    ).group_by(Prediction.bank_name).order_by(func.count(Prediction.id).desc()).limit(5).all()
    
    return jsonify({
        'period': 'last_7_days',
        'total_predictions': total,
        'alerts_generated': alerts,
        'alert_rate': round(alerts / total * 100, 2) if total > 0 else 0,
        'model_usage': {
            'crisis_mode': crisis_mode_usage,
            'rare_event_mode': rare_mode_usage,
            'crisis_percentage': round(crisis_mode_usage / total * 100, 2) if total > 0 else 0
        },
        'avg_probability': round(sum(p.stress_probability for p in recent_predictions) / total, 4) if total > 0 else 0,
        'top_banks_alerts': [{'bank': bank, 'count': count} for bank, count in top_banks]
    })


# ============================================
# ERROR HANDLERS
# ============================================

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Endpoint not found'}), 404


@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return jsonify({'error': 'Internal server error'}), 500


# ============================================
# CREATE DATABASE TABLES
# ============================================

with app.app_context():
    db.create_all()
    app.logger.info("Database tables created/verified")


# ============================================
# RUN APPLICATION
# ============================================

if __name__ == '__main__':
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=False,
        threaded=True
    )