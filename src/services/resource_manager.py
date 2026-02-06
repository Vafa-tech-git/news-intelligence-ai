import psutil
import os
import gc
import threading
import time
import logging
from typing import Dict, Optional, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

@dataclass
class ResourceLimits:
    """Resource usage limits"""
    max_memory_percent: float = 80.0
    max_cpu_percent: float = 90.0
    max_disk_usage_percent: float = 85.0
    max_concurrent_operations: int = 10

@dataclass
class ResourceUsage:
    """Current resource usage"""
    memory_percent: float
    cpu_percent: float
    disk_usage_percent: float
    active_threads: int
    open_files: int
    timestamp: datetime

class ResourceManager:
    """Monitor and manage system resources"""
    
    def __init__(self, limits: Optional[ResourceLimits] = None):
        self.limits = limits or ResourceLimits()
        self.process = psutil.Process(os.getpid())
        self.monitoring = False
        self.monitor_thread = None
        self.resource_history = []
        self.max_history_size = 100
        
        # Resource control
        self.active_operations = 0
        self.operation_lock = threading.Lock()
        
        # Alert thresholds
        self.memory_thresholds = [70, 80, 90]  # Warning levels
        self.cpu_thresholds = [60, 80, 95]
        
        # Cleanup callbacks
        self.cleanup_callbacks = []
    
    def start_monitoring(self, interval: int = 30):
        """Start resource monitoring"""
        if self.monitoring:
            return
        
        self.monitoring = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, args=(interval,))
        self.monitor_thread.daemon = True
        self.monitor_thread.start()
        
        logger.info("Resource monitoring started")
    
    def stop_monitoring(self):
        """Stop resource monitoring"""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
        logger.info("Resource monitoring stopped")
    
    def _monitor_loop(self, interval: int):
        """Main monitoring loop"""
        while self.monitoring:
            try:
                usage = self.get_current_usage()
                self.resource_history.append(usage)
                
                # Limit history size
                if len(self.resource_history) > self.max_history_size:
                    self.resource_history = self.resource_history[-self.max_history_size:]
                
                # Check thresholds and take action
                self._check_thresholds(usage)
                
                # Perform periodic cleanup
                if len(self.resource_history) % 10 == 0:
                    self._perform_maintenance()
                
            except Exception as e:
                logger.error(f"Resource monitoring error: {e}")
            
            time.sleep(interval)
    
    def get_current_usage(self) -> ResourceUsage:
        """Get current resource usage"""
        try:
            # Memory usage
            memory_info = self.process.memory_info()
            memory_percent = self.process.memory_percent()
            
            # CPU usage
            cpu_percent = self.process.cpu_percent()
            
            # Disk usage
            disk_usage = psutil.disk_usage('/').percent
            
            # Thread count
            active_threads = self.process.num_threads()
            
            # Open files
            try:
                open_files = len(self.process.open_files())
            except:
                open_files = 0
            
            return ResourceUsage(
                memory_percent=memory_percent,
                cpu_percent=cpu_percent,
                disk_usage_percent=disk_usage,
                active_threads=active_threads,
                open_files=open_files,
                timestamp=datetime.now()
            )
            
        except Exception as e:
            logger.error(f"Error getting resource usage: {e}")
            return ResourceUsage(0, 0, 0, 0, 0, datetime.now())
    
    def _check_thresholds(self, usage: ResourceUsage):
        """Check resource usage against thresholds"""
        # Memory checks
        for threshold in self.memory_thresholds:
            if usage.memory_percent >= threshold:
                level = "CRITICAL" if threshold >= 90 else "WARNING"
                logger.log(
                    logging.CRITICAL if threshold >= 90 else logging.WARNING,
                    f"Memory usage {usage.memory_percent:.1f}% exceeds threshold {threshold}%"
                )
                
                if threshold >= 90:
                    self._emergency_memory_cleanup()
                break
        
        # CPU checks
        for threshold in self.cpu_thresholds:
            if usage.cpu_percent >= threshold:
                level = "CRITICAL" if threshold >= 95 else "WARNING"
                logger.log(
                    logging.CRITICAL if threshold >= 95 else logging.WARNING,
                    f"CPU usage {usage.cpu_percent:.1f}% exceeds threshold {threshold}%"
                )
                
                if threshold >= 95:
                    self._emergency_cpu_throttling()
                break
        
        # Disk checks
        if usage.disk_usage_percent >= self.limits.max_disk_usage_percent:
            logger.critical(f"Disk usage {usage.disk_usage_percent:.1f}% exceeds limit")
            self._emergency_disk_cleanup()
    
    def _emergency_memory_cleanup(self):
        """Emergency memory cleanup"""
        logger.warning("Performing emergency memory cleanup")
        
        # Force garbage collection
        gc.collect()
        
        # Clear caches
        try:
            from src.utils.cache import cache_manager
            if cache_manager.enabled:
                cache_manager.redis_client.flushdb()
                logger.info("Cleared Redis cache")
        except:
            pass
        
        # Clear in-memory caches
        try:
            from src.services.optimized_news_service import optimized_fetcher
            optimized_fetcher.feed_cache.clear()
            logger.info("Cleared RSS feed cache")
        except:
            pass
        
        # Call cleanup callbacks
        for callback in self.cleanup_callbacks:
            try:
                callback()
            except Exception as e:
                logger.error(f"Cleanup callback error: {e}")
    
    def _emergency_cpu_throttling(self):
        """Emergency CPU throttling"""
        logger.warning("Performing emergency CPU throttling")
        
        # Reduce concurrent operations
        with self.operation_lock:
            original_limit = self.limits.max_concurrent_operations
            self.limits.max_concurrent_operations = max(1, original_limit // 2)
            logger.info(f"Reduced concurrent operations from {original_limit} to {self.limits.max_concurrent_operations}")
    
    def _emergency_disk_cleanup(self):
        """Emergency disk cleanup"""
        logger.warning("Performing emergency disk cleanup")
        
        try:
            from src.core.database import get_db_connection
            # Clean up very old news
            deleted = db_service.cleanup_old_news(days_old=7)
            logger.info(f"Emergency cleanup deleted {deleted} old articles")
        except Exception as e:
            logger.error(f"Disk cleanup error: {e}")
    
    def _perform_maintenance(self):
        """Perform periodic maintenance"""
        logger.debug("Performing resource maintenance")
        
        # Garbage collection
        collected = gc.collect()
        if collected > 0:
            logger.debug(f"Garbage collected {collected} objects")
        
        # Reset failed feeds periodically
        try:
            from src.services.optimized_news_service import optimized_fetcher
            optimized_fetcher.reset_failed_feeds()
        except:
            pass
    
    def can_start_operation(self) -> bool:
        """Check if a new operation can start"""
        with self.operation_lock:
            if self.active_operations >= self.limits.max_concurrent_operations:
                return False
            
            # Check resource limits
            usage = self.get_current_usage()
            if (usage.memory_percent >= self.limits.max_memory_percent or
                usage.cpu_percent >= self.limits.max_cpu_percent):
                return False
            
            self.active_operations += 1
            return True
    
    def end_operation(self):
        """Mark an operation as completed"""
        with self.operation_lock:
            if self.active_operations > 0:
                self.active_operations -= 1
    
    def add_cleanup_callback(self, callback: Callable):
        """Add cleanup callback"""
        self.cleanup_callbacks.append(callback)
    
    def get_performance_report(self) -> Dict:
        """Get comprehensive performance report"""
        if not self.resource_history:
            return {'status': 'No data available'}
        
        # Calculate averages
        avg_memory = sum(r.memory_percent for r in self.resource_history) / len(self.resource_history)
        avg_cpu = sum(r.cpu_percent for r in self.resource_history) / len(self.resource_history)
        
        # Peak usage
        peak_memory = max(r.memory_percent for r in self.resource_history)
        peak_cpu = max(r.cpu_percent for r in self.resource_history)
        
        # Current usage
        current = self.get_current_usage()
        
        # Recommendations
        recommendations = []
        
        if avg_memory > 70:
            recommendations.append("Consider increasing memory or optimizing memory usage")
        
        if avg_cpu > 60:
            recommendations.append("Consider optimizing CPU-intensive operations")
        
        if self.active_operations >= self.limits.max_concurrent_operations * 0.8:
            recommendations.append("High operation concurrency detected")
        
        return {
            'current_usage': {
                'memory_percent': current.memory_percent,
                'cpu_percent': current.cpu_percent,
                'disk_usage_percent': current.disk_usage_percent,
                'active_threads': current.active_threads,
                'open_files': current.open_files,
                'active_operations': self.active_operations
            },
            'averages': {
                'memory_percent': avg_memory,
                'cpu_percent': avg_cpu
            },
            'peaks': {
                'memory_percent': peak_memory,
                'cpu_percent': peak_cpu
            },
            'limits': {
                'max_memory_percent': self.limits.max_memory_percent,
                'max_cpu_percent': self.limits.max_cpu_percent,
                'max_concurrent_operations': self.limits.max_concurrent_operations
            },
            'monitoring_active': self.monitoring,
            'history_count': len(self.resource_history),
            'recommendations': recommendations
        }

# Resource usage decorator
def manage_resource_usage(operation_name: str):
    """Decorator to manage resource usage for operations"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            if not resource_manager.can_start_operation():
                logger.warning(f"Resource limits exceeded, skipping {operation_name}")
                return None
            
            try:
                start_time = time.time()
                result = func(*args, **kwargs)
                end_time = time.time()
                
                logger.debug(f"{operation_name} completed in {end_time - start_time:.2f}s")
                return result
            finally:
                resource_manager.end_operation()
        
        return wrapper
    return decorator

# Global resource manager instance
resource_manager = ResourceManager()

# Auto-start monitoring
resource_manager.start_monitoring()

if __name__ == "__main__":
    # Test resource manager
    logger.info("🧪 Testing resource manager...")
    
    # Get current usage
    usage = resource_manager.get_current_usage()
    logger.info(f"📊 Current usage: {usage}")
    
    # Get performance report
    report = resource_manager.get_performance_report()
    logger.info(f"📈 Performance report: {report}")
    
    # Test operation management
    @manage_resource_usage("test_operation")
    def test_operation():
        time.sleep(2)
        return "success"
    
    result = test_operation()
    logger.info(f"✅ Test operation result: {result}")
    
    resource_manager.stop_monitoring()
