import re
from typing import Dict, Any


class PlanNotFound(Exception):
    """Exception raised when a plan is not found"""
    pass


class DuplicateSlugError(Exception):
    """Exception raised when a duplicate slug is detected"""
    pass


class ValidationError(Exception):
    """Exception raised for validation errors"""
    pass


def generate_slug(name: str) -> str:
    """
    Convert plan name to URL-safe slug
    
    Args:
        name: Plan name
        
    Returns:
        URL-safe slug string
    """
    # Convert to lowercase
    slug = name.lower()
    
    # Replace spaces and underscores with hyphens
    slug = re.sub(r'[\s_]+', '-', slug)
    
    # Remove special characters
    slug = re.sub(r'[^a-z0-9-]', '', slug)
    
    # Remove multiple consecutive hyphens
    slug = re.sub(r'-+', '-', slug)
    
    # Remove leading/trailing hyphens
    slug = slug.strip('-')
    
    return slug


def format_price(price_cents: int, currency: str = "USD") -> str:
    """
    Convert price in cents to formatted string
    
    Args:
        price_cents: Price in cents
        currency: Currency code (USD, GBP, INR)
        
    Returns:
        Formatted price string
    """
    if price_cents < 0:
        return "Custom Pricing"
    
    price_dollars = price_cents / 100
    
    symbols = {
        "USD": "$",
        "GBP": "£",
        "INR": "₹"
    }
    
    symbol = symbols.get(currency, "$")
    
    # Format with appropriate decimal places
    if currency == "INR":
        # Indian numbering system
        return f"{symbol}{price_dollars:,.2f}"
    else:
        return f"{symbol}{price_dollars:,.2f}"


def validate_modules_json(modules: Dict[str, Any]) -> bool:
    """
    Validate modules_json structure
    
    Args:
        modules: Dictionary of module flags
        
    Returns:
        True if valid, raises ValidationError if invalid
    """
    if not isinstance(modules, dict):
        raise ValidationError("modules_json must be a dictionary")
    
    # Check that all values are boolean
    for key, value in modules.items():
        if not isinstance(key, str):
            raise ValidationError(f"Module key '{key}' must be a string")
        if not isinstance(value, bool):
            raise ValidationError(f"Module value for '{key}' must be a boolean")
    
    return True


def calculate_yearly_savings(monthly_price: int, yearly_price: int) -> int:
    """
    Calculate savings when choosing yearly billing
    
    Args:
        monthly_price: Monthly price in cents
        yearly_price: Yearly price in cents
        
    Returns:
        Savings in cents
    """
    monthly_total = monthly_price * 12
    savings = monthly_total - yearly_price
    
    return max(0, savings)


def is_plan_available_in_region(plan_regions: list, user_region: str) -> bool:
    """
    Check if plan is available in user's region
    
    Args:
        plan_regions: List of allowed regions
        user_region: User's region code
        
    Returns:
        True if plan is available in region
    """
    if not plan_regions or "ALL" in plan_regions:
        return True
    
    return user_region.upper() in [r.upper() for r in plan_regions]
