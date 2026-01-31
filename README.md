# 📈 AI News Intelligence

An application for real-time monitoring and analysis of financial markets, using Artificial Intelligence (Ollama) and advanced Web scraping.

## 🌟 Features

- **RSS Monitoring:** Automatically scans feeds from Yahoo Finance, CNBC, WSJ, TechCrunch, etc.
- **Smart Scraping:** Uses a hybrid method (Requests + Playwright) to extract content even from difficult sites or those with Lazy Loading.
- **AI Analysis:** Summarizes news and calculates an "Impact score" (0-10) for markets using the `gpt-oss:120b` model.
- **Bookmarks:** System for saving important news that persists after database resets.
- **Modern Interface:** Clean UI built with Tailwind CSS and HTMX for interactivity without refresh.

## 🛠️ Technologies Used

- **Backend:** Python (Flask)
- **Database:** SQLite
- **AI:** Ollama
- **Frontend:** HTML, Tailwind CSS, HTMX
- **Scraping:** BeautifulSoup4, Playwright

## 🚀 Installation and Running

1. **Clone the repository:**
   ```bash
   git clone https://github.com/Vafa-tech-git/news-intelligence-ai.git
   cd news-intelligence-ai
   ```

2. **Create the virtual environment:**
   ```bash
   python -m venv env
   source env/bin/activate  # On Windows: env\Scripts\activate
   ```

3. **Configure the .env file: Create a .env file and add:**
   ```
   OLLAMA_HOST=https://ollama.com
   OLLAMA_KEY=
   OLLAMA_MODEL=gpt-oss:120b-cloud

   FINNHUB_TOKEN=
   ```

4. **Start the server:**
   ```bash
   python app.py
   ```