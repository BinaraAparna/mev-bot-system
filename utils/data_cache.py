"""
Data Cache
Local caching to reduce RPC calls and API requests
"""

import time
import sqlite3
import json
from typing import Any, Optional
from loguru import logger


class DataCache:
    """
    Local SQLite cache for reducing external API/RPC calls
    Critical for free tier optimization
    """
    
    def __init__(self, db_path: str = "data/cache/mev_bot.db"):
        """
        Initialize Data Cache
        
        Args:
            db_path: Path to SQLite database
        """
        self.db_path = db_path
        self.conn = None
        
        # Initialize database
        self._init_db()
        
        logger.info(f"Data Cache initialized: {db_path}")
    
    def _init_db(self):
        """Initialize SQLite database"""
        try:
            # Create directory if needed
            import os
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            
            # Connect to database
            self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            cursor = self.conn.cursor()
            
            # Create cache table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS cache (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    ttl INTEGER NOT NULL
                )
            ''')
            
            # Create index on timestamp for cleanup
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_timestamp ON cache(timestamp)
            ''')
            
            self.conn.commit()
            
            logger.success("Cache database initialized")
            
        except Exception as e:
            logger.error(f"Error initializing cache database: {e}")
    
    def set(self, key: str, value: Any, ttl: int = 60):
        """
        Set cache value
        
        Args:
            key: Cache key
            value: Value to cache (will be JSON serialized)
            ttl: Time to live in seconds
        """
        try:
            # Serialize value
            value_json = json.dumps(value)
            
            # Current timestamp
            timestamp = time.time()
            
            # Insert or replace
            cursor = self.conn.cursor()
            cursor.execute(
                'INSERT OR REPLACE INTO cache (key, value, timestamp, ttl) VALUES (?, ?, ?, ?)',
                (key, value_json, timestamp, ttl)
            )
            self.conn.commit()
            
            logger.debug(f"Cache set: {key} (TTL: {ttl}s)")
            
        except Exception as e:
            logger.error(f"Error setting cache: {e}")
    
    def get(self, key: str) -> Optional[Any]:
        """
        Get cache value
        
        Args:
            key: Cache key
            
        Returns:
            Cached value or None if expired/missing
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                'SELECT value, timestamp, ttl FROM cache WHERE key = ?',
                (key,)
            )
            
            row = cursor.fetchone()
            
            if not row:
                return None
            
            value_json, timestamp, ttl = row
            
            # Check if expired
            age = time.time() - timestamp
            if age > ttl:
                # Expired - delete and return None
                self.delete(key)
                return None
            
            # Deserialize and return
            value = json.loads(value_json)
            logger.debug(f"Cache hit: {key} (age: {age:.1f}s)")
            
            return value
            
        except Exception as e:
            logger.debug(f"Error getting cache: {e}")
            return None
    
    def delete(self, key: str):
        """
        Delete cache entry
        
        Args:
            key: Cache key
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute('DELETE FROM cache WHERE key = ?', (key,))
            self.conn.commit()
            
        except Exception as e:
            logger.error(f"Error deleting cache: {e}")
    
    def clear_expired(self):
        """Clear all expired cache entries"""
        try:
            current_time = time.time()
            
            cursor = self.conn.cursor()
            cursor.execute(
                'DELETE FROM cache WHERE timestamp + ttl < ?',
                (current_time,)
            )
            
            deleted = cursor.rowcount
            self.conn.commit()
            
            if deleted > 0:
                logger.info(f"Cleared {deleted} expired cache entries")
            
        except Exception as e:
            logger.error(f"Error clearing expired cache: {e}")
    
    def clear_all(self):
        """Clear entire cache"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('DELETE FROM cache')
            self.conn.commit()
            
            logger.warning("Cache cleared")
            
        except Exception as e:
            logger.error(f"Error clearing cache: {e}")
    
    def get_stats(self) -> dict:
        """
        Get cache statistics
        
        Returns:
            Stats dict
        """
        try:
            cursor = self.conn.cursor()
            
            # Total entries
            cursor.execute('SELECT COUNT(*) FROM cache')
            total = cursor.fetchone()[0]
            
            # Expired entries
            current_time = time.time()
            cursor.execute(
                'SELECT COUNT(*) FROM cache WHERE timestamp + ttl < ?',
                (current_time,)
            )
            expired = cursor.fetchone()[0]
            
            # Database size
            cursor.execute('SELECT page_count * page_size FROM pragma_page_count(), pragma_page_size()')
            size_bytes = cursor.fetchone()[0]
            
            return {
                'total_entries': total,
                'valid_entries': total - expired,
                'expired_entries': expired,
                'size_bytes': size_bytes,
                'size_kb': size_bytes / 1024
            }
            
        except Exception as e:
            logger.error(f"Error getting cache stats: {e}")
            return {}
    
    def __del__(self):
        """Cleanup on deletion"""
        if self.conn:
            self.conn.close()