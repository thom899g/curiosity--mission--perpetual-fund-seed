"""
Hydra Allocation Engine - PID controller-inspired yield optimizer
Implements weighted scoring algorithm with safety constraints
"""
import logging
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
import yaml
import json

# Try importing Firebase manager
try:
    from core.firebase_manager import FirebaseManager, AllocationState
    FIREBASE_MANAGER_AVAILABLE = True
except ImportError as e:
    logging.warning(f"Firebase manager not available: {e}")
    FIREBASE_MANAGER_AVAILABLE = False

# Configure logging
logger = logging.getLogger(__name__)


@dataclass
class MarketMetrics:
    """Data class for market metrics"""
    gas_prices: Dict[str, float]  # Gwei per chain
    yield_differentials: Dict[str, float]  # APR spreads
    volatility_indices: Dict[str, float]  # 0-100 scale
    tvl_changes: Dict[str, float]  # Percentage change
    timestamp: datetime


@dataclass
class AllocationScore:
    """Data class for allocation scores"""
    chain: str
    strategy: str
    base_score: float
    gas_adjusted_score: float
    risk_adjusted_score: float
    final_score: float
    recommended_allocation: float


class HydraAllocationEngine:
    """
    PID controller-inspired allocation engine using on-chain metrics
    Dynamically adjusts allocations based on real-time market conditions
    """
    
    def __init__(self, config_path: str = "config/hydra_config.yaml"):
        """
        Initialize allocation engine
        
        Args:
            config_path: Path to configuration YAML file
        """
        # Load configuration
        self.config = self._load_config(config_path)
        if not self.config:
            raise ValueError(f"Failed to load config from {config_path}")
        
        # Initialize Firebase manager
        self.firebase_manager: Optional[FirebaseManager] = None
        if FIREBASE_MANAGER_AVAILABLE:
            self.firebase_manager = FirebaseManager()
        
        # PID controller parameters (tuned for DeFi yield optimization)
        self.pid_params = {
            'kp': 0.8,  # Proportional gain