# 📈 News AI Intelligence - Financial AI Platform

A comprehensive financial intelligence platform for real-time market monitoring using Artificial Intelligence (Ollama) and advanced web scraping.

## 🌟 Key Features

### 📰 Extensive News Monitoring
- **International Sources:** Yahoo Finance, CNBC, Investing.com, BBC Business, TechCrunch, Fortune, CoinDesk, and more
- **Romanian Sources:** Ziarul Financiar, Profit.ro, Bursa.ro, Wall-Street.ro, Economica.net, CursDeGuvernare.ro
- **Geographic Categorization:** Automatic separation between international and Romanian news
- **Multi-threading:** Parallel scanning for maximum performance (4-20 configurable threads)

### 🤖 Advanced Financial Intelligence
- **AI Analysis:** Summarization and impact scoring (1-10) using `gpt-oss:120b-cloud` model
- **Instrument Detection:** Automatic identification of Romanian stock symbols (SNG, BRD, TLV, etc.)
- **Trading Recommendations:** Buy/Sell/Hold with confidence scores
- **Sentiment Analysis:** Positive/Negative/Neutral for each article

### 🔍 Advanced Filtering and Sorting
- **Multi-criteria Filters:** Impact score, financial instruments, recommendations, sentiment
- **Flexible Sorting:** By impact or date (toggleable)
- **Category Tabs:** Internal (Romania) vs External (International) news
- **Instrument Filtering:** Show only news relevant to selected instruments

### 📧 Automatic Email Alerts
- **High Impact Alerts:** Automatic email for news with impact ≥ 9
- **SMTP Configuration:** Full support for Gmail and other SMTP servers
- **Rate Limiting:** Protection against spam with minimum interval between alerts
- **Professional Templates:** HTML emails with all relevant details

### 🎨 Modern Interface
- **Responsive Design:** Works perfectly on desktop and mobile
- **Dark Theme:** Optimized interface for long-term usage
- **Advanced News Cards:** Complete information about trading decisions
- **Visual Indicators:** Colors and emojis for quick identification

## 🛠️ Technologies

### Backend
- **Python 3.8+:** Main development language
- **Flask:** Lightweight and flexible web framework
- **SQLite:** Local relational database with connection pooling
- **Ollama:** Local AI platform (preferred) with cloud fallback

### Frontend
- **HTML5 + Tailwind CSS:** Modern responsive design
- **HTMX:** Dynamic interactions without JavaScript framework
- **Alpine.js:** Lightweight client-side interactivity

### Integration & Performance
- **Multi-threading:** Parallel processing with 4-20 configurable workers
- **Connection Pooling:** Optimized database connections
- **Caching:** Multi-layer caching for AI results and web content
- **Background Tasks:** Celery for async processing

### Security
- **CSRF Protection:** Cross-site request forgery prevention
- **Rate Limiting:** Configurable limits per endpoint
- **Input Sanitization:** XSS prevention with Bleach
- **Secure Headers:** Security-focused HTTP headers
- **Session Security:** HTTPOnly, Secure, SameSite cookies

## 🚀 Quick Start

### Prerequisites
- **Python 3.8+** with pip
- **Redis** (optional, for rate limiting)
- **Ollama** (optional, for local AI processing)

### Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd news_ai_app
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

5. **Initialize database**
   ```bash
   python -c "from src.core.database import init_database; init_database()"
   ```

6. **Run the application**
   ```bash
   python run.py
   ```

The application will be available at `http://localhost:5002`

## ⚙️ Configuration

### Environment Variables

Copy `.env.example` to `.env` and configure:

#### **Required for Basic Functionality:**
- `SECRET_KEY`: Generate with `python -c "import secrets; print(secrets.token_hex(32))"`
- `FINNHUB_TOKEN`: Get from [Finnhub](https://finnhub.io/)

#### **For AI Analysis:**
- `OLLAMA_KEY`: Get from [Ollama Cloud](https://ollama.com/) (cloud AI)
- `LOCAL_OLLAMA_PREFERRED`: Set to `True` to use local Ollama first

#### **For Email Alerts:**
- `EMAIL_ALERTS_ENABLED`: Set to `True` to enable alerts
- `SMTP_USERNAME` / `SMTP_PASSWORD`: Your email credentials
- `DEFAULT_ALERT_RECIPIENT`: Email address for alerts

#### **For Production:**
- `HTTPS_ENABLED`: Set to `True` for production
- `DEBUG_MODE`: Set to `False` for production

### Performance Tuning

#### **Multi-threading:**
- `MAX_WORKER_THREADS`: Number of parallel workers (default: 4)
- `ENABLE_PARALLEL_PROCESSING`: Enable/disable parallel processing

#### **Caching:**
- `ENABLE_ENHANCED_CACHING`: Enable multi-layer caching
- `CACHE_TTL_HOURS_AI`: AI result cache duration (default: 24h)

#### **Rate Limiting:**
- `RATELIMIT_ENABLED`: Enable/disable rate limiting
- `RATELIMIT_DEFAULT`: Default limits (default: "200 per day, 50 per hour")

### Performance Features
- **Connection Pooling:** 15 database connections in pool
- **Batch Processing:** 25 articles per batch
- **Parallel Workers:** 4-20 configurable threads
- **Memory Management:** Automatic cleanup of old data

### Performance Monitoring
The application includes built-in performance monitoring:
- Memory usage tracking
- CPU utilization monitoring
- Database query performance
- Request timing

### Security Features
- CSRF token protection on all forms
- Rate limiting per endpoint
- Input sanitization with Bleach
- Secure session management
- SQL injection prevention

## 🔍 Troubleshooting

### Common Issues

**Application doesn't start:**
- Check Python version (3.8+ required)
- Verify all dependencies installed: `pip install -r requirements.txt`
- Check .env file exists and is configured

**No news appearing:**
- Verify FINNHUB_TOKEN is valid
- Check internet connection
- Review logs for errors

**AI analysis not working:**
- Check Ollama configuration
- Verify OLLAMA_KEY for cloud AI
- Test AI service: `python -c "from src.services.ai_service_market_enhanced import analyze_article_with_market_data; print('OK')"`

**Email alerts not sending:**
- Verify SMTP credentials
- Check email app passwords (use app-specific passwords for Gmail)
- Verify EMAIL_ALERTS_ENABLED=True

**Performance issues:**
- Adjust MAX_WORKER_THREADS down
- Enable caching: `ENABLE_ENHANCED_CACHING=True`
- Monitor memory usage

### Debug Mode
Enable debug mode for detailed logging:
```bash
DEBUG_MODE=True python run.py
```

### Log Files
Check these log files for issues:
- `logs/app.json`: General application logs
- `logs/security.log`: Security-related events
- Console output for real-time monitoring

## 🤝 Contributing

1. Fork the repository
2. Create feature branch: `git checkout -b feature-name`
3. Make changes and test thoroughly
4. Commit changes: `git commit -am "Add feature"`
5. Push to fork: `git push origin feature-name`
6. Create Pull Request

### Development Guidelines
- Follow PEP 8 style guidelines
- Add proper error handling
- Include comprehensive logging
- Test all changes
- Update documentation

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🔗 Links

- **Ollama AI:** [https://ollama.com/](https://ollama.com/)
- **Finnhub API:** [https://finnhub.io/](https://finnhub.io/)
- **Flask Framework:** [https://flask.palletsprojects.com/](https://flask.palletsprojects.com/)

## 📊 System Requirements

### Minimum Requirements
- **Python:** 3.8+
- **Memory:** 512MB RAM
- **Storage:** 100MB free space
- **Network:** Internet connection for news fetching

### Recommended Requirements
- **Python:** 3.9+
- **Memory:** 2GB RAM
- **Storage:** 1GB free space
- **Network:** Stable internet connection
- **Optional:** Redis for rate limiting
- **Optional:** Local Ollama for AI processing

---

**Note:** This application is designed to work locally without requiring external services. All sensitive configuration is stored in environment variables, and no deployment tools are included for security.