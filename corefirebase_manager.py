"""
Firebase state manager for Hydra Fund
Handles all database operations with robust error handling and logging
"""
import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict
from enum import Enum

# Firebase Admin SDK
try:
    import firebase_admin
    from firebase_admin import credentials, firestore, initialize_app
    from google.cloud.firestore_v1 import Client as FirestoreClient
    FIREBASE_AVAILABLE = True
except ImportError as e:
    logging.warning(f"Firebase Admin not available: {e}")
    FIREBASE_AVAILABLE = False

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class FirebaseOperation(Enum):
    """Firebase operation types for tracking"""
    READ = "read"
    WRITE = "write"
    UPDATE = "update"
    DELETE = "delete"


@dataclass
class AllocationState:
    """Data class for allocation state"""
    chain: str
    strategy: str
    current_allocation: float
    target_allocation: float
    actual_apr: float
    tvl_usd: float
    last_updated: datetime
    health_score: float  # 0-1 scale


class FirebaseManager:
    """Manages all Firebase Firestore operations for Hydra Fund"""
    
    def __init__(self, credential_path: Optional[str] = None):
        """
        Initialize Firebase connection
        
        Args:
            credential_path: Path to Firebase service account JSON file
                           If None, uses GOOGLE_APPLICATION_CREDENTIALS env var
        """
        self.db: Optional[FirestoreClient] = None
        self.initialized = False
        
        try:
            if not FIREBASE_AVAILABLE:
                raise ImportError("firebase_admin package not installed")
            
            # Initialize Firebase app (only once)
            if not firebase_admin._apps:
                if credential_path:
                    cred = credentials.Certificate(credential_path)
                else:
                    cred = credentials.ApplicationDefault()
                
                firebase_admin.initialize_app(cred)
            
            self.db = firestore.client()
            self.initialized = True
            logger.info("Firebase Firestore initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize Firebase: {e}")
            self.initialized = False
    
    def log_operation(self, operation: FirebaseOperation, 
                     collection: str, document: str,
                     success: bool, error: Optional[str] = None) -> None:
        """Log Firebase operations for auditing"""
        log_data = {
            'timestamp': datetime.utcnow().isoformat(),
            'operation': operation.value,
            'collection': collection,
            'document': document,
            'success': success,
            'error': error
        }
        
        if success:
            logger.debug(f"Firebase {operation.value} on {collection}/{document}")
        else:
            logger.error(f"Firebase {operation.value} failed: {error}")
        
        # Also write to operations log collection
        if self.initialized and self.db:
            try:
                self.db.collection('firebase_operations').add(log_data)
            except Exception as e:
                logger.error(f"Failed to log operation: {e}")
    
    def save_allocation_state(self, state: AllocationState) -> bool:
        """
        Save allocation state to Firebase
        
        Args:
            state: AllocationState object
            
        Returns:
            bool: Success status
        """
        if not self.initialized or not self.db:
            logger.error("Firebase not initialized")
            return False
        
        try:
            # Convert dataclass to dict
            state_dict = asdict(state)
            state_dict['last_updated'] = state_dict['last_updated'].isoformat()
            
            # Create document reference
            doc_ref = self.db.collection('allocation_states').document(
                f"{state.chain}_{state.strategy}"
            )
            
            # Set with merge to preserve other fields
            doc_ref.set(state_dict, merge=True)
            
            self.log_operation(
                FirebaseOperation.WRITE,
                'allocation_states',
                f"{state.chain}_{state.strategy}",
                True
            )
            return True
            
        except Exception as e:
            error_msg = f"Failed to save allocation state: {e}"
            logger.error(error_msg)
            self.log_operation(
                FirebaseOperation.WRITE,
                'allocation_states',
                f"{state.chain}_{state.strategy}",
                False,
                error_msg
            )
            return False
    
    def get_allocation_state(self, chain: str, strategy: str) -> Optional[Dict[str, Any]]:
        """
        Get allocation state from Firebase
        
        Args:
            chain: Chain name
            strategy: Strategy name
            
        Returns:
            Dict with state or None if not found
        """
        if not self.initialized or not self.db:
            logger.error("Firebase not initialized")
            return None
        
        try:
            doc_ref = self.db.collection('allocation_states').document(
                f"{chain}_{strategy}"
            )
            doc = doc_ref.get()
            
            if doc.exists:
                data = doc.to_dict()
                self.log_operation(
                    FirebaseOperation.READ,
                    'allocation_states',
                    f"{chain}_{strategy}",
                    True
                )
                return data
            else:
                logger.warning(f"No allocation state found for {chain}_{strategy}")
                return None
                
        except Exception as e:
            error_msg = f"Failed to get allocation state: {e}"
            logger.error(error_msg)
            self.log_operation(
                FirebaseOperation.READ,
                'allocation_states',
                f"{chain}_{strategy}",
                False,
                error_msg
            )
            return None
    
    def update_market_metrics(self, metrics: Dict[str, Any]) -> bool:
        """
        Update market metrics in Firebase
        
        Args:
            metrics: Dictionary of market metrics
            
        Returns:
            bool: Success status
        """
        if not self.initialized or not self.db:
            logger.error("Firebase not initialized")
            return False
        
        try:
            # Add timestamp
            metrics['timestamp'] = datetime.utcnow().isoformat()
            
            # Save to market_metrics collection
            doc_ref = self.db.collection('market_metrics').document('latest')
            doc_ref.set(metrics, merge=True)
            
            # Also add to history
            history_ref = self.db.collection('market_metrics_history').document()
            history_ref.set(metrics)
            
            self.log_operation(
                FirebaseOperation.UPDATE,
                'market_metrics',
                'latest',
                True
            )
            return True
            
        except Exception as e:
            error_msg = f"Failed to update market metrics: {e}"
            logger.error(error_msg)
            self.log_operation(
                FirebaseOperation.UPDATE,
                'market_metrics',
                'latest',
                False,
                error_msg
            )
            return False
    
    def get_market_metrics(self) -> Optional[Dict[str, Any]]:
        """
        Get latest market metrics from Firebase
        
        Returns:
            Dict with metrics or None if not found
        """
        if not self.initialized or not self.db:
            logger.error("Firebase not initialized")
            return None
        
        try:
            doc_ref = self.db.collection('market_metrics').document('latest')
            doc = doc_ref.get()
            
            if doc.exists:
                self.log_operation(
                    FirebaseOperation.READ,
                    'market_metrics',
                    'latest',
                    True
                )
                return doc.to_dict()
            else:
                logger.warning("No market metrics found")
                return None
                
        except Exception as e:
            error_msg = f"Failed to get market metrics: {e}"
            logger.error(error_msg)
            self.log_operation(
                FirebaseOperation.READ,
                'market_metrics',
                'latest',
                False,
                error_msg
            )
            return None
    
    def set_harvest_conditions(self, chain: str, conditions: Dict[str, Any]) -> bool:
        """
        Set harvest conditions for a specific chain
        
        Args:
            chain: Chain name
            conditions: Dictionary of harvest conditions
            
        Returns:
            bool: Success status
        """
        if not self.initialized or not self.db:
            logger.error("Firebase not initialized")
            return False
        
        try:
            # Add timestamp
            conditions['last_updated'] = datetime.utcnow().isoformat()
            
            # Save to harvest_conditions collection
            doc_ref = self.db.collection('harvest_conditions').document(chain)
            doc_ref.set(conditions, merge=True)
            
            self.log_operation(
                FirebaseOperation.WRITE,
                'harvest_conditions',
                chain,
                True
            )
            return True
            
        except Exception as e:
            error_msg = f"Failed to set harvest conditions: {e}"
            logger.error(error_msg)
            self.log_operation(
                FirebaseOperation.WRITE,
                'harvest_conditions',
                chain,
                False,
                error_msg
            )
            return False
    
    def get_harvest_conditions(self, chain: str) -> Optional[Dict[str, Any]]:
        """
        Get harvest conditions for a specific chain
        
        Args:
            chain: Chain name
            
        Returns:
            Dict with conditions or None if not found
        """
        if not self.initialized or not self.db:
            logger.error("Firebase not initialized")
            return None
        
        try:
            doc_ref = self.db.collection('harvest_conditions').document(chain)
            doc = doc_ref.get()
            
            if doc.exists:
                self.log_operation(
                    FirebaseOperation.READ,
                    'harvest_conditions',
                    chain,
                    True
                )
                return doc.to_dict()
            else:
                logger.warning(f"No harvest conditions found for {chain}")
                return None
                
        except Exception as e:
            error_msg = f"Failed to get harvest conditions: {e}"
            logger.error(error_msg)
            self.log_operation(
                FirebaseOperation.READ,
                'harvest_conditions',
                chain,
                False,
                error_msg
            )
            return None
    
    def close(self) -> None:
        """Close Firebase connection"""
        if self.initialized:
            logger.info("Firebase connection closed")
            # Note: Firebase doesn't require explicit closing in Python
            self.initialized = False