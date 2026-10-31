"""
Schema definitions for Super Admin Dashboard API
"""
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime


# ============================================
# METRIC CARDS SCHEMAS
# ============================================

class MetricCardData(BaseModel):
    """Individual metric card data"""
    value: int | float
    change: str = Field(..., description="Percentage change, e.g., '+12%'")
    trend: str = Field(..., description="Trend direction: up, down, neutral")
    currency: Optional[str] = None
    period: Optional[str] = None
    severity: Optional[str] = None


class MetricCards(BaseModel):
    """All metric cards for dashboard"""
    total_tenants: MetricCardData
    active_tenants: MetricCardData
    trial_tenants: MetricCardData
    mrr: MetricCardData
    arr: MetricCardData
    payroll_runs: MetricCardData
    failed_payments: MetricCardData
    api_errors: MetricCardData
    security_flags: MetricCardData


# ============================================
# CHART DATA SCHEMAS
# ============================================

class ChartDataset(BaseModel):
    """Dataset for line/bar charts"""
    label: str
    data: List[int | float]
    color: Optional[str] = None


class LineChartData(BaseModel):
    """Line chart data structure"""
    type: str = "line"
    labels: List[str]
    datasets: List[ChartDataset]


class StackedBarChartData(BaseModel):
    """Stacked bar chart data structure"""
    type: str = "stackedBar"
    labels: List[str]
    datasets: List[ChartDataset]


class GeographicDataPoint(BaseModel):
    """Geographic distribution data point"""
    country: str
    country_code: str
    tenants: int
    revenue: float
    coordinates: Dict[str, float] = Field(..., description="lat and lng")


class GeographicDistributionData(BaseModel):
    """Geographic distribution map data"""
    type: str = "map"
    data: List[GeographicDataPoint]


class HeatmapHourData(BaseModel):
    """Hour data for heatmap"""
    hour: int = Field(..., ge=0, le=23)
    value: int


class HeatmapDayData(BaseModel):
    """Day data for heatmap"""
    day: str
    hours: List[HeatmapHourData]


class UserActivityData(BaseModel):
    """User activity heatmap data"""
    type: str = "heatmap"
    data: List[HeatmapDayData]


class FunnelStage(BaseModel):
    """Funnel chart stage"""
    name: str
    value: int
    percentage: float


class TrialFunnelData(BaseModel):
    """Trial funnel chart data"""
    type: str = "funnel"
    stages: List[FunnelStage]


class DonutSegment(BaseModel):
    """Donut chart segment"""
    label: str
    value: int
    percentage: float
    color: str


class SubscriptionStatusData(BaseModel):
    """Subscription status donut chart data"""
    type: str = "donut"
    data: List[DonutSegment]


class SecurityEventsData(BaseModel):
    """Security events line chart data"""
    type: str = "line"
    labels: List[str]
    datasets: List[ChartDataset]


# ============================================
# MAIN RESPONSE SCHEMAS
# ============================================

class DashboardCharts(BaseModel):
    """All dashboard charts"""
    tenant_growth: LineChartData
    revenue_by_plan: StackedBarChartData
    geographic_distribution: GeographicDistributionData
    user_activity: UserActivityData
    trial_funnel: TrialFunnelData
    subscription_status: SubscriptionStatusData
    security_events: SecurityEventsData


class DashboardData(BaseModel):
    """Dashboard data container"""
    metric_cards: MetricCards
    charts: DashboardCharts
    last_updated: datetime


class DashboardStatsResponse(BaseModel):
    """Main dashboard stats response"""
    success: bool = True
    data: DashboardData
