# Bank EWS — API Reference

Base URL: `http://localhost:5000`

---

## GET `/`

Returns service info and lists all available endpoints.

**Response:**
```json
{
  "service": "Bank Early Warning System",
  "version": "2.0.0",
  "status": "operational",
  "models_loaded": true,
  "endpoints": {
    "predict": "/api/v1/predict",
    "batch_predict": "/api/v1/predict/batch",
    "health": "/api/v1/health",
    "model_info": "/api/v1/model/info",
    "predictions": "/api/v1/predictions",
    "dashboard_stats": "/api/v1/dashboard/stats",
    "dashboard": "/dashboard"
  }
}
```

---

## GET `/api/v1/health`

Health check endpoint.

**Response:**
```json
{
  "status": "healthy",
  "models_loaded": true,
  "database_connected": true,
  "timestamp": "2024-12-01T10:30:00.000000+00:00"
}
```

---

## GET `/api/v1/model/info`

Returns model metadata, feature importance rankings, thresholds, and performance metrics.

---

## POST `/api/v1/predict`

Predict stress for a single bank.

### Request Body

```json
{
  "bank_name": "SBI",
  "year": 2024,
  "stress_prevalence": 0.10,
  "features": {
    "crar_total": 14.5,
    "npa_ratio": 9.5,
    "total_provisions": 5000,
    "net_profit": 1200,
    "interest_income": 15000,
    "interest_expense": 8000,
    "operating_expense": 4000,
    "credit_growth": 12.5,
    "repo_rate": 6.5,
    "inflation": 4.8
  }
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `bank_name` | string | ✅ | Name of the bank |
| `year` | integer | ✅ | Prediction year |
| `stress_prevalence` | float | ❌ | Override auto-detection of model mode (0-1) |
| `features` | object | ✅ | All 10 financial features |

### Response (200)

```json
{
  "bank_name": "SBI",
  "year": 2024,
  "stress_probability": 0.7234,
  "stress_prediction": true,
  "alert": true,
  "threshold_used": 0.5,
  "mode": "crisis",
  "model_version": "2.0.0",
  "risk_factors": [
    "High NPA: 9.5% > 8%"
  ],
  "prediction_id": 42,
  "timestamp": "2024-12-01T10:30:00.000000+00:00",
  "response_time_ms": 12.34
}
```

### Error Responses

| Status | Reason |
|--------|--------|
| 400 | Missing required fields or features |
| 503 | Models not loaded |
| 500 | Internal prediction error |

---

## POST `/api/v1/predict/batch`

Predict stress for multiple banks (max 50).

### Request Body

```json
{
  "stress_prevalence": 0.10,
  "banks": [
    {
      "bank_name": "SBI",
      "year": 2024,
      "features": { ... }
    },
    {
      "bank_name": "HDFC",
      "year": 2024,
      "features": { ... }
    }
  ]
}
```

### Response (200)

```json
{
  "predictions": [ ... ],
  "errors": null,
  "mode": "rare",
  "threshold_used": 0.85,
  "summary": {
    "total": 2,
    "stressed": 1,
    "healthy": 1,
    "stressed_percentage": 50.0
  },
  "response_time_ms": 25.67
}
```

---

## GET `/api/v1/predictions`

Retrieve historical predictions with pagination.

### Query Parameters

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `page` | int | 1 | Page number |
| `per_page` | int | 50 | Results per page |
| `bank_name` | string | — | Filter by bank name (partial match) |

### Example

```
GET /api/v1/predictions?bank_name=SBI&page=1&per_page=10
```

---

## GET `/api/v1/dashboard/stats`

Returns aggregated statistics for the last 7 days.

### Response (200)

```json
{
  "period": "last_7_days",
  "total_predictions": 150,
  "alerts_generated": 23,
  "alert_rate": 15.33,
  "model_usage": {
    "crisis_mode": 100,
    "rare_event_mode": 50,
    "crisis_percentage": 66.67
  },
  "avg_probability": 0.3456,
  "top_banks_alerts": [
    { "bank": "SBI", "count": 5 }
  ]
}
```

---

## GET `/dashboard`

Serves the interactive HTML dashboard for making predictions via a web form.

---

## Feature Descriptions

All 10 features are required for predictions:

| Feature | Unit | RBI Threshold |
|---------|------|---------------|
| `crar_total` | % | < 10.5% = at risk |
| `npa_ratio` | % | > 8% = at risk |
| `total_provisions` | ₹ Crore | — |
| `net_profit` | ₹ Crore | < 0 = loss-making |
| `interest_income` | ₹ Crore | — |
| `interest_expense` | ₹ Crore | — |
| `operating_expense` | ₹ Crore | — |
| `credit_growth` | % | > 20% = aggressive |
| `repo_rate` | % | Macro indicator |
| `inflation` | % | Macro indicator |
