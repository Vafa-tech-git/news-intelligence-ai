# State Management Service
import json
import logging
from typing import Dict, Any, Optional
from flask import session, request

logger = logging.getLogger(__name__)

class NewsStateManager:
    """Enhanced state manager for persistent user preferences"""
    
    STORAGE_KEY = 'news_app_state_v2'
    
    def __init__(self):
        self.default_state = {
            'current_category': 'international',
            'current_sort': 'impact',
            'filters': {
                'impact_min': 1,
                'impact_max': 10,
                'recommendation': '',
                'category': 'international'
            },
            'ui_preferences': {
                'theme': 'auto',
                'auto_refresh': False,
                'compact_view': False
            },
            'continuous_scan': {
                'enabled': False,
                'last_scan': None,
                'next_scan': None,
                'scan_interval': 900,  # 15 minutes in seconds
                'scan_category': 'all'
            }
        }
    
    def load_state(self) -> Dict[str, Any]:
        """Load state from multiple sources with fallback"""
        try:
            # Priority 1: Server session
            if 'news_state' in session:
                logger.info("Loading state from server session")
                session_state = json.loads(session['news_state'])
                merged_state = {**self.default_state, **session_state}
                return merged_state
            
            # Priority 2: Local storage (for persistence across sessions)
            import requests
            try:
                # Try to load from localStorage via request headers
                local_storage_state = request.headers.get('X-Local-State')
                if local_storage_state:
                    logger.info("Loading state from localStorage")
                    local_state = json.loads(local_storage_state)
                    merged_state = {**self.default_state, **local_state}
                    return merged_state
            except:
                pass
            
            # Priority 3: Default state
            logger.info("Using default state")
            return self.default_state.copy()
            
        except Exception as e:
            logger.error(f"Error loading state: {e}")
            return self.default_state.copy()
    
    def save_state(self, updates: Dict[str, Any], persistent: bool = True) -> bool:
        """Save state updates with persistence option"""
        try:
            # Update current state
            current_state = self.load_state()
            new_state = {**current_state, **updates}
            
            # Save to server session
            session['news_state'] = json.dumps(new_state)
            logger.info(f"Saved state to server session: {list(updates.keys())}")
            
            # Save to localStorage for persistence (if requested)
            if persistent:
                logger.info("State saved with persistence flag")
                # Note: This will be handled client-side via JavaScript
            
            return True
            
        except Exception as e:
            logger.error(f"Error saving state: {e}")
            return False
    
    def get_category_preferences(self) -> Dict[str, Any]:
        """Get user's category preferences"""
        state = self.load_state()
        return {
            'current_category': state.get('current_category', 'international'),
            'preferred_categories': state.get('preferred_categories', ['international']),
            'category_stats': state.get('category_stats', {})
        }
    
    def update_category_preference(self, category: str) -> bool:
        """Update user's preferred category with persistence"""
        if category not in ['international', 'romania', 'global']:
            logger.warning(f"Invalid category: {category}")
            return False
        
        updates = {
            'current_category': category,
            'filters.category': category,
            'last_category_change': self._get_timestamp()
        }
        
        return self.save_state(updates, persistent=True)
    
    def preserve_filters_during_scan(self) -> Dict[str, Any]:
        """Preserve current filters when scanning"""
        current_state = self.load_state()
        
        # Create scan-preserved state
        preserved_filters = current_state.get('filters', {}).copy()
        preserved_preferences = current_state.get('ui_preferences', {}).copy()
        
        scan_state = {
            'current_category': current_state.get('current_category'),
            'filters': preserved_filters,
            'ui_preferences': preserved_preferences,
            'scan_in_progress': True,
            'scan_timestamp': self._get_timestamp()
        }
        
        return scan_state
    
    def restore_filters_after_scan(self, scan_results: Dict[str, Any]) -> bool:
        """Restore filters after scan completion"""
        try:
            # Get the preserved state from scan results
            current_state = self.load_state()
            
            if scan_results.get('scan_in_progress', False):
                logger.info("No scan in progress, nothing to restore")
                return True
            
            # Restore saved filters
            updates = {
                'scan_in_progress': False,
                'scan_completed_at': self._get_timestamp(),
                'filters': scan_results.get('filters', current_state.get('filters', {})),
                'ui_preferences': scan_results.get('ui_preferences', current_state.get('ui_preferences', {}))
            }
            
            return self.save_state(updates, persistent=True)
            
        except Exception as e:
            logger.error(f"Error restoring filters after scan: {e}")
            return False
    
    def get_filter_state(self) -> Dict[str, Any]:
        """Get current filter state"""
        state = self.load_state()
        return {
            'active_filters': state.get('filters', {}),
            'filter_count': len([k for k, v in state.get('filters', {}).items() if v]),
            'has_active_filters': any(state.get('filters', {}).values()),
            'category': state.get('filters', {}).get('category', 'international'),
            'impact_range': {
                'min': state.get('filters', {}).get('impact_min', 1),
                'max': state.get('filters', {}).get('impact_max', 10)
            }
        }
    
    def update_filter_value(self, filter_type: str, value: Any) -> bool:
        """Update individual filter value"""
        try:
            current_filters = self.load_state().get('filters', {})
            updated_filters = {**current_filters, filter_type: value}
            
            updates = {
                'filters': updated_filters,
                'last_filter_change': self._get_timestamp()
            }
            
            return self.save_state(updates, persistent=True)
            
        except Exception as e:
            logger.error(f"Error updating filter {filter_type}: {e}")
            return False
    
    def get_sort_preference(self) -> str:
        """Get current sort preference"""
        state = self.load_state()
        return state.get('current_sort', 'impact')
    
    def update_sort_preference(self, sort_type: str) -> bool:
        """Update sort preference"""
        if sort_type not in ['impact', 'date', 'published_at']:
            return False
        
        updates = {
            'current_sort': sort_type,
            'last_sort_change': self._get_timestamp()
        }
        
        return self.save_state(updates, persistent=True)

    def _calculate_time_until_next_scan(self, scan_state: Dict[str, Any]) -> int:
        """Calculate seconds until next scan"""
        if not scan_state.get('enabled') or not scan_state.get('next_scan'):
            return -1
        
        from datetime import datetime
        try:
            next_scan_time = datetime.fromisoformat(scan_state['next_scan'].replace('Z', '+00:00'))
            now = datetime.utcnow()
            delta = next_scan_time - now
            return max(0, int(delta.total_seconds()))
        except:
            return -1
    
    def get_ui_state(self) -> Dict[str, Any]:
        """Get UI state for rendering"""
        state = self.load_state()
        return {
            'current_category': state.get('current_category', 'international'),
            'current_sort': state.get('current_sort', 'impact'),
            'active_filters': state.get('filters', {}),
            'ui_preferences': state.get('ui_preferences', {}),
            'is_scanning': state.get('scan_in_progress', False),
            'last_update': state.get('last_category_change', '')
        }
    
    def export_state(self) -> Dict[str, Any]:
        """Export complete state for backup"""
        state = self.load_state()
        return {
            'export_timestamp': self._get_timestamp(),
            'version': '2.0',
            'state': state
        }
    
    def import_state(self, exported_state: Dict[str, Any]) -> bool:
        """Import exported state"""
        try:
            updates = {
                'imported_at': self._get_timestamp(),
                'state': exported_state.get('state', {})
            }
            
            return self.save_state(updates, persistent=True)
            
        except Exception as e:
            logger.error(f"Error importing state: {e}")
            return False
    
    def _get_timestamp(self) -> str:
        """Get current timestamp"""
        from datetime import datetime
        return datetime.now().isoformat()

# Global state manager instance
state_manager = NewsStateManager()

def get_global_state_manager():
    """Get global state manager instance"""
    return state_manager