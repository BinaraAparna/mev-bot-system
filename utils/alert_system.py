"""
Alert System
Sends email notifications for critical events
"""

import os
import smtplib
import asyncio
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
from loguru import logger
from dotenv import load_dotenv

load_dotenv()


class AlertSystem:
    """
    Email alert system for critical events
    Uses Gmail SMTP (free)
    """
    
    def __init__(self):
        """Initialize Alert System"""
        # SMTP configuration
        self.smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
        self.smtp_port = int(os.getenv('SMTP_PORT', '587'))
        self.smtp_username = os.getenv('SMTP_USERNAME')
        self.smtp_password = os.getenv('SMTP_APP_PASSWORD')
        
        # Alert recipient
        self.alert_email = os.getenv('ALERT_EMAIL', 'binaraedu20@gmail.com')
        
        # Rate limiting (avoid spam)
        self.last_alert_time = {}
        self.min_alert_interval = 300  # 5 minutes between same alerts
        
        # Validate configuration
        if not all([self.smtp_username, self.smtp_password]):
            logger.warning("SMTP credentials not configured - alerts disabled")
            self.enabled = False
        else:
            self.enabled = True
            logger.info(f"Alert System initialized - sending to {self.alert_email}")
    
    async def send_alert(
        self,
        subject: str,
        message: str,
        priority: str = 'normal'
    ) -> bool:
        """
        Send email alert
        
        Args:
            subject: Email subject
            message: Email body
            priority: 'low', 'normal', 'high', 'critical'
            
        Returns:
            True if sent successfully
        """
        if not self.enabled:
            logger.debug(f"Alert disabled: {subject}")
            return False
        
        # Check rate limiting
        if not self._should_send_alert(subject, priority):
            logger.debug(f"Alert rate limited: {subject}")
            return False
        
        try:
            # Create email
            msg = MIMEMultipart()
            msg['From'] = self.smtp_username
            msg['To'] = self.alert_email
            msg['Subject'] = f"[MEV Bot - {priority.upper()}] {subject}"
            
            # Add priority header
            if priority == 'critical':
                msg['X-Priority'] = '1'
            elif priority == 'high':
                msg['X-Priority'] = '2'
            
            # Email body
            body = f"""
MEV Bot Alert
==============

Priority: {priority.upper()}
Time: {asyncio.get_event_loop().time()}

{message}

---
This is an automated message from your MEV Bot.
"""
            
            msg.attach(MIMEText(body, 'plain'))
            
            # Send email
            await asyncio.get_event_loop().run_in_executor(
                None,
                self._send_email_sync,
                msg
            )
            
            # Update rate limit
            self.last_alert_time[subject] = asyncio.get_event_loop().time()
            
            logger.info(f"Alert sent: {subject}")
            return True
            
        except Exception as e:
            logger.error(f"Error sending alert: {e}")
            return False
    
    def _send_email_sync(self, msg: MIMEMultipart):
        """Synchronous email sending (called in executor)"""
        with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
            server.starttls()
            server.login(self.smtp_username, self.smtp_password)
            server.send_message(msg)
    
    def _should_send_alert(self, subject: str, priority: str) -> bool:
        """
        Check if alert should be sent (rate limiting)
        
        Args:
            subject: Alert subject
            priority: Alert priority
            
        Returns:
            True if should send
        """
        # Always send critical alerts
        if priority == 'critical':
            return True
        
        # Check rate limit for other priorities
        if subject in self.last_alert_time:
            time_since_last = asyncio.get_event_loop().time() - self.last_alert_time[subject]
            
            if time_since_last < self.min_alert_interval:
                return False
        
        return True
    
    async def send_critical_alert(self, subject: str, message: str) -> bool:
        """Send critical priority alert"""
        return await self.send_alert(subject, message, priority='critical')
    
    async def send_profit_alert(self, profit_usd: float, strategy: str) -> bool:
        """
        Send profit notification
        
        Args:
            profit_usd: Profit amount in USD
            strategy: Strategy that generated profit
            
        Returns:
            True if sent
        """
        subject = f"Profit: ${profit_usd:.2f} from {strategy}"
        message = f"""
Successful Trade Alert
=====================

Strategy: {strategy}
Profit: ${profit_usd:.2f} USD

Great job! Your bot just executed a profitable trade.
"""
        
        return await self.send_alert(subject, message, priority='normal')
    
    async def send_loss_alert(self, loss_usd: float, reason: str) -> bool:
        """
        Send loss notification
        
        Args:
            loss_usd: Loss amount in USD
            reason: Reason for loss
            
        Returns:
            True if sent
        """
        subject = f"Loss: ${loss_usd:.2f}"
        message = f"""
Trade Loss Alert
===============

Loss Amount: ${loss_usd:.2f} USD
Reason: {reason}

Your bot experienced a loss. This is normal, but monitor closely.
"""
        
        return await self.send_alert(subject, message, priority='high')
    
    async def send_rpc_failover_alert(self, from_tier: str, to_tier: str) -> bool:
        """
        Send RPC failover notification
        
        Args:
            from_tier: Tier that failed
            to_tier: Tier switched to
            
        Returns:
            True if sent
        """
        subject = f"RPC Failover: {from_tier} → {to_tier}"
        message = f"""
RPC Tier Failover
=================

Failed Tier: {from_tier}
Switched To: {to_tier}

Your bot switched RPC tiers due to rate limiting or connection issues.
This is normal behavior, but monitor RPC usage.
"""
        
        priority = 'critical' if to_tier == 'tier_4' else 'high'
        
        return await self.send_alert(subject, message, priority=priority)
    
    async def send_kill_switch_alert(self, reason: str, stats: dict) -> bool:
        """
        Send kill switch activation alert
        
        Args:
            reason: Reason for activation
            stats: Bot statistics
            
        Returns:
            True if sent
        """
        subject = "KILL SWITCH ACTIVATED"
        message = f"""
EMERGENCY KILL SWITCH ACTIVATED
================================

Reason: {reason}

Bot Statistics:
- Total Trades: {stats.get('total_trades', 0)}
- Successful: {stats.get('successful_trades', 0)}
- Failed: {stats.get('failed_trades', 0)}
- Total Profit: ${stats.get('total_profit_usd', 0):.2f}
- Gas Spent: ${stats.get('gas_spent_usd', 0):.2f}

IMMEDIATE ACTION REQUIRED!

Your bot has been automatically paused due to safety conditions.
Please investigate immediately.
"""
        
        return await self.send_alert(subject, message, priority='critical')
    
    async def send_daily_summary(self, stats: dict) -> bool:
        """
        Send daily performance summary
        
        Args:
            stats: Daily statistics
            
        Returns:
            True if sent
        """
        subject = f"Daily Summary - Profit: ${stats.get('daily_profit', 0):.2f}"
        message = f"""
Daily Performance Summary
========================

Date: {stats.get('date', 'Today')}

Trading Performance:
- Total Trades: {stats.get('total_trades', 0)}
- Successful: {stats.get('successful_trades', 0)}
- Failed: {stats.get('failed_trades', 0)}
- Success Rate: {stats.get('success_rate', 0):.1f}%

Financial Summary:
- Total Profit: ${stats.get('daily_profit', 0):.2f}
- Gas Spent: ${stats.get('gas_spent', 0):.2f}
- Net Profit: ${stats.get('net_profit', 0):.2f}

Strategy Breakdown:
- Direct Arbitrage: {stats.get('direct_arb_count', 0)} trades
- Triangular: {stats.get('triangular_count', 0)} trades
- Flashloan: {stats.get('flashloan_count', 0)} trades
- Sandwich: {stats.get('sandwich_count', 0)} trades
- Liquidation: {stats.get('liquidation_count', 0)} trades

Keep up the great work!
"""
        
        return await self.send_alert(subject, message, priority='low')
    
    async def test_alert(self) -> bool:
        """Send test alert to verify configuration"""
        subject = "Test Alert - Configuration OK"
        message = """
This is a test alert from your MEV Bot.

If you're receiving this, your alert system is configured correctly!
"""
        
        return await self.send_alert(subject, message, priority='normal')