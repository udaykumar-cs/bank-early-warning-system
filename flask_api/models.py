from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timezone

db = SQLAlchemy()

class Prediction(db.Model):
    """Store all predictions for audit and monitoring"""
    __tablename__ = 'predictions'
    
    id = db.Column(db.Integer, primary_key=True)
    bank_name = db.Column(db.String(100), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    
    # Input features
    crar_total = db.Column(db.Float)
    npa_ratio = db.Column(db.Float)
    total_provisions = db.Column(db.Float)
    net_profit = db.Column(db.Float)
    interest_income = db.Column(db.Float)
    interest_expense = db.Column(db.Float)
    operating_expense = db.Column(db.Float)
    credit_growth = db.Column(db.Float)
    repo_rate = db.Column(db.Float)
    inflation = db.Column(db.Float)
    
    # Prediction results
    stress_probability = db.Column(db.Float, nullable=False)
    stress_prediction = db.Column(db.Boolean, nullable=False)
    threshold_used = db.Column(db.Float, nullable=False)
    model_version = db.Column(db.String(20))
    mode_used = db.Column(db.String(20))  # 'crisis' or 'rare_event'
    
    # Metadata
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.String(200))
    prediction_time_ms = db.Column(db.Float)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    def to_dict(self):
        return {
            'id': self.id,
            'bank_name': self.bank_name,
            'year': self.year,
            'stress_probability': self.stress_probability,
            'stress_prediction': self.stress_prediction,
            'threshold_used': self.threshold_used,
            'model_version': self.model_version,
            'mode_used': self.mode_used,
            'created_at': self.created_at.isoformat()
        }


class ModelPerformance(db.Model):
    """Track model performance over time"""
    __tablename__ = 'model_performance'
    
    id = db.Column(db.Integer, primary_key=True)
    model_version = db.Column(db.String(20), nullable=False)
    mode = db.Column(db.String(20))
    date = db.Column(db.Date, nullable=False)
    
    # Daily metrics
    total_predictions = db.Column(db.Integer, default=0)
    total_alerts = db.Column(db.Integer, default=0)
    avg_probability = db.Column(db.Float)
    
    # Weekly aggregated metrics (to be updated from actual outcomes)
    actual_stress_rate = db.Column(db.Float)
    precision = db.Column(db.Float)
    recall = db.Column(db.Float)
    
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


class ApiLog(db.Model):
    """Log all API requests for debugging"""
    __tablename__ = 'api_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    endpoint = db.Column(db.String(100))
    method = db.Column(db.String(10))
    status_code = db.Column(db.Integer)
    response_time_ms = db.Column(db.Float)
    ip_address = db.Column(db.String(45))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))