"""
MEV Bot - Main Entry Point
Advanced Multi-Strategy MEV Bot for Polygon
"""

import asyncio
import signal
import sys
from loguru import logger
from bot.bot_engine import MEVBotEngine

# Configure logging
logger.remove()
logger.add(
    sys.stderr,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
    level="INFO"
)
logger.add(
    "data/logs/bot.log",
    rotation="1 day",
    retention="7 days",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function} - {message}",
    level="DEBUG"
)


class MEVBotRunner:
    """Main bot runner with signal handling"""
    
    def __init__(self):
        """Initialize bot runner"""
        self.bot = None
        self.running = False
    
    async def start(self):
        """Start the bot"""
        try:
            logger.info("=" * 70)
            logger.info("🚀 MEV Bot Starting...")
            logger.info("=" * 70)
            
            # Initialize bot engine
            self.bot = MEVBotEngine(config_path="config/bot_config.json")
            
            # Register signal handlers
            signal.signal(signal.SIGINT, self._signal_handler)
            signal.signal(signal.SIGTERM, self._signal_handler)
            
            self.running = True
            
            # Start bot
            await self.bot.start()
            
        except KeyboardInterrupt:
            logger.info("Received interrupt signal")
            await self.stop()
        except Exception as e:
            logger.error(f"Fatal error: {e}", exc_info=True)
            await self.stop()
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        logger.info(f"Received signal {signum}")
        
        if self.running:
            asyncio.create_task(self.stop())
    
    async def stop(self):
        """Stop the bot gracefully"""
        if not self.running:
            return
        
        logger.info("=" * 70)
        logger.info("🛑 Shutting down MEV Bot...")
        logger.info("=" * 70)
        
        self.running = False
        
        if self.bot:
            # Get final stats
            stats = self.bot.get_stats()
            
            logger.info("\n📊 Final Statistics:")
            logger.info(f"  Uptime: {stats['uptime_hours']:.2f} hours")
            logger.info(f"  Total Trades: {stats['total_trades']}")
            logger.info(f"  Successful: {stats['successful_trades']}")
            logger.info(f"  Failed: {stats['failed_trades']}")
            logger.info(f"  Success Rate: {stats['success_rate']:.1f}%")
            logger.info(f"  Total Profit: ${stats['total_profit_usd']:.2f}")
            logger.info(f"  Gas Spent: ${stats['gas_spent_usd']:.2f}")
            
            # Emergency shutdown
            await self.bot.emergency_shutdown()
        
        logger.info("=" * 70)
        logger.info("✅ Shutdown complete")
        logger.info("=" * 70)


async def main():
    """Main entry point"""
    runner = MEVBotRunner()
    await runner.start()


if __name__ == "__main__":
    try:
        # Run bot
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error in main: {e}", exc_info=True)
    finally:
        logger.info("MEV Bot terminated")