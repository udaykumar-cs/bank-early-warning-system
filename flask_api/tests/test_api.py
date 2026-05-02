import pytest
import json
import sys
import os

# Add the parent directory to sys.path so we can import app
sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

from app import app, db

@pytest.fixture
def client():
    # Configure app for testing
    app.config['TESTING'] = True
    # In-memory database for testing
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    
    with app.test_client() as client:
        with app.app_context():
            db.create_all()
        yield client
        with app.app_context():
            db.drop_all()

def test_health_check(client):
    """Test the health check endpoint."""
    response = client.get('/api/v1/health')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['status'] == 'healthy'
    assert 'models_loaded' in data

def test_predict_valid_input(client):
    """Test prediction with valid input data."""
    valid_data = {
        "bank_name": "Test Bank",
        "year": 2024,
        "features": {
            "crar_total": 14.5,
            "npa_ratio": 5.0,
            "total_provisions": 5000,
            "net_profit": 1000,
            "interest_income": 10000,
            "interest_expense": 5000,
            "operating_expense": 2000,
            "credit_growth": 10.0,
            "repo_rate": 6.5,
            "inflation": 5.0
        }
    }
    response = client.post(
        '/api/v1/predict',
        data=json.dumps(valid_data),
        content_type='application/json'
    )
    assert response.status_code == 200
    data = json.loads(response.data)
    assert 'stress_probability' in data
    assert 'stress_prediction' in data
    assert data['bank_name'] == 'Test Bank'

def test_predict_missing_features(client):
    """Test prediction with missing features."""
    invalid_data = {
        "bank_name": "Test Bank",
        "year": 2024,
        "features": {
            "crar_total": 14.5
            # Missing other features
        }
    }
    response = client.post(
        '/api/v1/predict',
        data=json.dumps(invalid_data),
        content_type='application/json'
    )
    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'error' in data
    assert 'Missing features' in data['error']

def test_predict_input_validation_npa(client):
    """Test validation rejection for impossible NPA ratio."""
    invalid_data = {
        "bank_name": "Test Bank",
        "year": 2024,
        "features": {
            "crar_total": 14.5,
            "npa_ratio": -5.0,  # Invalid: negative
            "total_provisions": 5000,
            "net_profit": 1000,
            "interest_income": 10000,
            "interest_expense": 5000,
            "operating_expense": 2000,
            "credit_growth": 10.0,
            "repo_rate": 6.5,
            "inflation": 5.0
        }
    }
    response = client.post(
        '/api/v1/predict',
        data=json.dumps(invalid_data),
        content_type='application/json'
    )
    assert response.status_code == 422
    data = json.loads(response.data)
    assert 'error' in data
    assert 'Input validation failed' in data['error']
    assert any('npa_ratio must be between' in d for d in data['details'])

def test_predict_input_validation_crar(client):
    """Test validation rejection for impossible CRAR."""
    invalid_data = {
        "bank_name": "Test Bank",
        "year": 2024,
        "features": {
            "crar_total": 250.0,  # Invalid: > 200
            "npa_ratio": 5.0,
            "total_provisions": 5000,
            "net_profit": 1000,
            "interest_income": 10000,
            "interest_expense": 5000,
            "operating_expense": 2000,
            "credit_growth": 10.0,
            "repo_rate": 6.5,
            "inflation": 5.0
        }
    }
    response = client.post(
        '/api/v1/predict',
        data=json.dumps(invalid_data),
        content_type='application/json'
    )
    assert response.status_code == 422
    data = json.loads(response.data)
    assert 'error' in data
    assert 'Input validation failed' in data['error']
    assert any('crar_total must be between' in d for d in data['details'])

def test_predict_input_validation_negative_provisions(client):
    """Test validation rejection for negative absolute values."""
    invalid_data = {
        "bank_name": "Test Bank",
        "year": 2024,
        "features": {
            "crar_total": 14.5,
            "npa_ratio": 5.0,
            "total_provisions": -5000,  # Invalid: negative absolute amount
            "net_profit": 1000,
            "interest_income": 10000,
            "interest_expense": 5000,
            "operating_expense": 2000,
            "credit_growth": 10.0,
            "repo_rate": 6.5,
            "inflation": 5.0
        }
    }
    response = client.post(
        '/api/v1/predict',
        data=json.dumps(invalid_data),
        content_type='application/json'
    )
    assert response.status_code == 422
    data = json.loads(response.data)
    assert 'error' in data
    assert 'Input validation failed' in data['error']
    assert any('cannot be negative' in d for d in data['details'])
