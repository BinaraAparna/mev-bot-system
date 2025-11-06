"""
Kill Switch
Emergency shutdown mechanism for risk management
"""

import time
from typing import Optional
from loguru import logger


class KillSwitch:
    """
    Emergency kill switch for bot protection
    
    Triggers on:
    - Daily loss exceeding limit
    - Too many failed transactions
    - Manual activation
    """
    
    def __init__(self, config: dict, alert_system):
        """
        Initialize Kill Switch
        
        Args:
            config: Bot configuration
            alert_system: Alert system for notifications
        """
        self.config = config
        self.alert_system = alert_system
        
        # Risk management settings
        self.max_daily_loss_usd = config['risk_management']['max_daily_loss_usd']
        self.max_failed_tx = config['risk_management']['max_failed_tx_before_pause']
        self.auto_kill_enabled = config['risk_management']['enable_auto_kill_switch']
        
        # State tracking
        self.triggered = False
        self.trigger_reason = None
        self.trigger_time = None
        
        # Daily tracking
        self.daily_loss = 0.0
        self.failed_tx_count = 0
        self.last_reset_day = self._get_current_day()
        
        logger.info(
            f"Kill Switch initialized - Max daily loss: ${self.max_daily_loss_usd}, "
            f"Max failed tx: {self.max_failed_tx}"
        )
    
    def _get_current_day(self) -> int:
        """Get current day number (for daily reset)"""
        return int(time.time() / 86400)  # Days since epoch
    
    def _reset_daily_counters(self):
        """Reset daily counters"""
        current_day = self._get_current_day()
        
        if current_day > self.last_reset_day:
            logger.info("Resetting daily counters")
            self.daily_loss = 0.0
            self.failed_tx_count = 0
            self.last_reset_day = current_day
    
    async def record_loss(self, loss_usd: float):
        """
        Record a trading loss
        
        Args:
            loss_usd: Loss amount in USD
        """
        self._reset_daily_counters()
        
        self.daily_loss += abs(loss_usd)
        
        logger.warning(f"Loss recorded: ${loss_usd:.2f} (Daily total: ${self.daily_loss:.2f})")
        
        # Check if limit exceeded
        if self.daily_loss >= self.max_daily_loss_usd:
            await self.trigger(f"Daily loss limit exceeded: ${self.daily_loss:.2f}")
    
    def record_failed_transaction(self):
        """Record a failed transaction"""
        self._reset_daily_counters()
        
        self.failed_tx_count += 1
        
        logger.warning(f"Failed transaction recorded (Count: {self.failed_tx_count})")
        
        # Check if limit exceeded
        if self.failed_tx_count >= self.max_failed_tx:
            # Don't trigger yet - just alert
            logger.critical(f"Failed transaction limit reached: {self.failed_tx_count}")
            
            # Send alert but don't auto-kill (give user chance to investigate)
            if self.alert_system:
                import asyncio
                asyncio.create_task(
                    self.alert_system.send_alert(
                        "Failed Transaction Limit Reached",
                        f"Bot has {self.failed_tx_count} failed transactions today. "
                        f"Consider investigating before continuing.",
                        priority='high'
                    )
                )
    
    async def trigger(self, reason: str):
        """
        Trigger the kill switch
        
        Args:
            reason: Reason for triggering
        """
        if self.triggered:
            logger.debug("Kill switch already triggered")
            return
        
        if not self.auto_kill_enabled:
            logger.warning(f"Kill switch trigger ignored (disabled): {reason}")
            return
        
        self.triggered = True
        self.trigger_reason = reason
        self.trigger_time = time.time()
        
        logger.critical(f"🚨 KILL SWITCH TRIGGERED: {reason}")
        
        # Send alert
        if self.alert_system:
            await self.alert_system.send_critical_alert(
                "KILL SWITCH ACTIVATED",
                f"Reason: {reason}\nBot operations halted for safety."
            )
    
    def is_triggered(self) -> bool:
        """Check if kill switch is triggered"""
        return self.triggered
    
    def check_daily_loss(self) -> bool:
        """
        Check if daily loss limit exceeded
        
        Returns:
            True if limit exceeded
        """
        self._reset_daily_counters()
        return self.daily_loss >= self.max_daily_loss_usd
    
    def get_status(self) -> dict:
        """
        Get kill switch status
        
        Returns:
            Status dict
        """
        self._reset_daily_counters()
        
        return {
            'triggered': self.triggered,
            'trigger_reason': self.trigger_reason,
            'trigger_time': self.trigger_time,
            'daily_loss_usd': self.daily_loss,
            'max_daily_loss_usd': self.max_daily_loss_usd,
            'daily_loss_percent': (self.daily_loss / self.max_daily_loss_usd) * 100,
            'failed_tx_count': self.failed_tx_count,
            'max_failed_tx': self.max_failed_tx,
            'auto_kill_enabled': self.auto_kill_enabled
        }
    
    def reset(self):
        """Reset kill switch (manual override)"""
        logger.warning("Kill switch manually reset")
        self.triggered = False
        self.trigger_reason = None
        self.trigger_time = None
    
    def manual_trigger(self, reason: str = "Manual activation"):
        """Manually trigger kill switch"""
        import asyncio
        asyncio.create_task(self.trigger(reason))