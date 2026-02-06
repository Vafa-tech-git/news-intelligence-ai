import smtplib
import ssl
import sys
import os
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from email.utils import formataddr

# Configure logging
logger = logging.getLogger(__name__)

# Import configuration
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.core.config import (
    SMTP_SERVER, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD, SMTP_USE_TLS,
    EMAIL_ALERTS_ENABLED, ALERT_HIGH_IMPACT_THRESHOLD, ALERT_RATE_LIMIT_MINUTES,
    DEFAULT_ALERT_RECIPIENT
)
from src.core.database import get_db_connection

class EmailAlertService:
    def __init__(self):
        self.last_sent_time = {}
        self.smtp_server = None
        self.is_connected = False
    
    def connect_smtp(self):
        """Connect to SMTP server"""
        try:
            context = ssl.create_default_context() if SMTP_USE_TLS else None
            
            self.smtp_server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
            
            if SMTP_USE_TLS:
                self.smtp_server.starttls(context=context)
            
            if SMTP_USERNAME and SMTP_PASSWORD:
                self.smtp_server.login(SMTP_USERNAME, SMTP_PASSWORD)
            
            self.is_connected = True
            logger.info(f"Successfully connected to SMTP server: {SMTP_SERVER}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to SMTP server: {e}")
            self.is_connected = False
            return False
    
    def disconnect_smtp(self):
        """Disconnect from SMTP server"""
        if self.smtp_server and self.is_connected:
            try:
                self.smtp_server.quit()
                logger.info("Disconnected from SMTP server")
            except:
                pass
            finally:
                self.is_connected = False
    
    def can_send_alert(self, recipient_email):
        """Check if we can send alert (rate limiting)"""
        if not EMAIL_ALERTS_ENABLED:
            return False, "Email alerts are disabled"
        
        current_time = datetime.now()
        if recipient_email in self.last_sent_time:
            time_diff = current_time - self.last_sent_time[recipient_email]
            if time_diff < timedelta(minutes=ALERT_RATE_LIMIT_MINUTES):
                wait_time = ALERT_RATE_LIMIT_MINUTES - int(time_diff.total_seconds() / 60)
                return False, f"Rate limit active. Wait {wait_time} minutes."
        
        return True, "Allowed"
    
    def create_alert_email(self, news_article, alert_type="high_impact"):
        """Create email content for news alert"""
        subject = f"🚨 Alertă financiară: {news_article['title'][:50]}..."
        
        # Determine emoji based on recommendation
        rec_emoji = {
            'strong_buy': '🟢🟢',
            'buy': '🟢', 
            'hold': '🟡',
            'sell': '🔴',
            'strong_sell': '🔴🔴'
        }
        
        recommendation = news_article.get('recommendation', 'N/A')
        emoji = rec_emoji.get(recommendation, '📊')
        
        html_content = f"""
        <html>
        <body style="font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5;">
            <div style="max-width: 600px; margin: 0 auto; background-color: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                
                <div style="text-align: center; margin-bottom: 30px;">
                    <h1 style="color: #333; margin: 0;">📰 News Intelligence AI</h1>
                    <p style="color: #666; margin: 5px 0;">Alertă de impact ridicat</p>
                </div>
                
                <div style="background-color: #fff3cd; border-left: 4px solid #ffc107; padding: 15px; margin-bottom: 20px;">
                    <h3 style="color: #856404; margin-top: 0;">🚨 ALERTĂ IMPACT {news_article.get('impact_score', 'N/A')}/10</h3>
                    <p style="color: #856404; margin-bottom: 0;">Această știre a fost detectată ca având impact critic asupra pieței.</p>
                </div>
                
                <div style="margin-bottom: 25px;">
                    <h2 style="color: #333; font-size: 18px; margin-bottom: 10px;">
                        <a href="{news_article['url']}" style="color: #0066cc; text-decoration: none;">
                            {news_article['title']}
                        </a>
                    </h2>
                    <div style="color: #666; font-size: 14px; margin-bottom: 15px;">
                        <strong>Sursă:</strong> {news_article['source']} | 
                        <strong>Data:</strong> {news_article.get('published_at', 'N/A')}
                    </div>
                </div>
                
                <div style="background-color: #f8f9fa; padding: 20px; border-radius: 8px; margin-bottom: 20px;">
                    <h3 style="color: #333; margin-top: 0;">📊 Analiză AI</h3>
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin-top: 15px;">
                        <div>
                            <strong>Recomandare:</strong> {emoji} {recommendation.upper()}<br>
                            <strong>Încredere:</strong> {news_article.get('confidence_score', 'N/A'):.1%}<br>
                            <strong>Sentiment:</strong> {news_article.get('sentiment', 'N/A')}
                        </div>
                        <div>
                            <strong>Impact:</strong> {news_article.get('impact_score', 'N/A')}/10<br>
                            <strong>Instrumente:</strong> {', '.join(news_article.get('instruments', [])) or 'N/A'}<br>
                            <strong>Categorie:</strong> {news_article.get('category', 'N/A')}
                        </div>
                    </div>
                </div>
                
                <div style="background-color: #e9ecef; padding: 15px; border-radius: 8px; margin-bottom: 20px;">
                    <h4 style="color: #333; margin-top: 0;">🔍 Rezumat AI</h4>
                    <p style="color: #555; line-height: 1.6; margin-bottom: 0;">
                        {news_article.get('ai_summary', 'N/A')}
                    </p>
                </div>
                
                <div style="text-align: center; margin-top: 30px;">
                    <a href="{news_article['url']}" 
                       style="background-color: #007bff; color: white; padding: 12px 25px; text-decoration: none; border-radius: 5px; display: inline-block; font-weight: bold;">
                        Citeste Articolul Complet
                    </a>
                </div>
                
                <div style="text-align: center; margin-top: 30px; padding-top: 20px; border-top: 1px solid #eee; color: #999; font-size: 12px;">
                    <p>Generat de News Intelligence AI • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                    <p>Aceasta este o alertă automată. Pentru a dezactiva, modificați setările în aplicație.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return subject, html_content
    
    def send_alert(self, news_article, recipient_email=None):
        """Send email alert for high-impact news"""
        recipient = recipient_email or DEFAULT_ALERT_RECIPIENT
        
        if not recipient:
            logger.warning("No recipient email configured")
            return False
        
        # Check if we should send alert
        can_send, reason = self.can_send_alert(recipient)
        if not can_send:
            logger.info(f"Alert not sent: {reason}")
            return False
        
        # Check impact threshold
        if news_article.get('impact_score', 0) < ALERT_HIGH_IMPACT_THRESHOLD:
            logger.info(f"Impact score {news_article.get('impact_score')} below threshold {ALERT_HIGH_IMPACT_THRESHOLD}")
            return False
        
        try:
            # Connect to SMTP if not already connected
            if not self.is_connected:
                if not self.connect_smtp():
                    return False
            
            # Create email
            subject, html_content = self.create_alert_email(news_article)
            
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = formataddr(('News Intelligence AI', SMTP_USERNAME or 'alerts@newsai.com'))
            msg['To'] = recipient
            
            # Attach HTML content
            html_part = MIMEText(html_content, 'html')
            msg.attach(html_part)
            
            # Send email
            self.smtp_server.send_message(msg)
            
            # Update last sent time
            self.last_sent_time[recipient] = datetime.now()
            
            # Log alert to database
            self.log_alert_to_db(news_article['id'], recipient, "high_impact", "sent")
            
            logger.info(f"Alert sent successfully to {recipient}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send alert: {e}")
            self.log_alert_to_db(news_article['id'], recipient, "high_impact", "failed", str(e))
            return False
    
    def log_alert_to_db(self, news_id, recipient_email, alert_type, status, error_message=None):
        """Log alert to database"""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO email_alerts (news_id, recipient_email, alert_type, status, error_message)
                    VALUES (?, ?, ?, ?, ?)
                ''', (news_id, recipient_email, alert_type, status, error_message))
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to log alert to database: {e}")

# Global instance
email_service = EmailAlertService()

def send_high_impact_alert(news_article):
    """Convenience function to send high-impact alert"""
    return email_service.send_alert(news_article)

def cleanup_email_service():
    """Cleanup SMTP connection"""
    email_service.disconnect_smtp()
