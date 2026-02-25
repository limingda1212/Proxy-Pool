# 🌐 ProxyPool

---

`Proxy Pool Management Project`

A comprehensive proxy pool management system supporting proxy collection, validation, management, security checks, and automated maintenance.

1.  Overview
2.  Quick Start
3.  Code Introduction
4.  Updates
5.  Notes

---

## 1. Overview:

### ✨ Features

#### 🚀 Core Functions
-   **Intelligent Proxy Collection**: Supports web scraping and local file import.
-   **Multi-level Validation Mechanisms**: Basic connectivity, browser usability, and security validation.
-   **Transparent Proxy Detection**: Automatically identifies proxies that leak your real IP.
-   **Smart Scoring System**: Dynamically scores proxies based on stability (0-100 points).
-   **Interruption Recovery**: Supports resuming after a validation process is interrupted.
-   **Automated Maintenance**: Cloud-based GitHub Actions for automatic proxy pool updates.

#### 🔧 Technical Features
-   **Multi-protocol Support**: HTTP/HTTPS/SOCKS4/SOCKS5.
-   **Asynchronous Validation**: High-performance asynchronous validation with concurrency support.
-   **SQLite Storage**: Lightweight database for storing complete proxy information.
-   **Web API**: Provides RESTful API endpoints.
-   **Cross-platform**: Supports Windows/macOS/Linux.

---

### 📁 Project Structure

This project consists of two parts: the `complete code deployed locally` and the `automated management code for cloud Actions in a public repository`.

**Note: The cloud code has been placed in the `cloud_deployment` folder of this repository.**

```
ProxyPool

├── <Cloud GitHub Actions> Proxy-Pool-Actions/
│      ├── actions_main.py
│      ├── proxies.csv
│      ├── README.md
│      ├── data/
│      │      └── config.json
│      └── .github/workflows/
│                      ├── Crawl-and-verify-new-proxies.yml
│                      └── Update-existing-proxies.yml
│
├── <Local> ProxyPool/
        ├── main.py                    # Main entry point
        │
        ├── core/                      # Core modules
        │   ├── __init__.py
        │   ├── config.py             # Configuration reading/saving
        │   └── menu.py               # Main menu
        │
        ├── collectors/                # Collection layer
        │   ├── __init__.py
        │   ├── web_crawler.py        # Web crawler
        │   └── file_loader.py        # File loader
        │
        ├── validators/                # Validation layer
        │   ├── __init__.py
        │   ├── base_validator.py     # Basic validation
        │   ├── browser_validator.py  # Browser validation
        │   └── security_checker.py   # Security validation
        │
        ├── schedulers/                # Scheduling layer
        │   ├── __init__.py
        │   ├── manual_scheduler.py   # Manual scheduling
        │   ├── api_server.py         # API service
        │   └── pool_monitor.py       # Proxy pool status monitoring
        │
        ├── storage/                   # Storage layer
        │   ├── __init__.py
        │   └── database.py           # Database operations
        │
        ├── sync/                      # Synchronization layer
        │   ├── __init__.py
        │   └── github_sync.py        # GitHub synchronization
        │
        ├── utils/                     # Utility functions
        │   ├── __init__.py
        │   ├── helpers.py            # General utilities
        │   ├── change_configs.py     # Modify settings
        │   ├── playwright_check.py   # Check Playwright installation
        │   ├── signal_manager.py     # Signal handling
        │   ├── use_api.py            # API usage
        │   └── interrupt_handler.py  # Interruption handling
        │
        ├── data/                      # Data files
        │   ├── config.json           # Configuration file
        │   ├── settings.py           # Data storage
        │   └── web/                  # Web files
        │       └── index.html
        │
        └── interrupt/                 # Interruption record directory
            └── *.csv
```

---

## 🚀 2. Quick Start

### Requirements
-   Python 3.8 or higher
-   Virtual environment recommended

### Installation Steps

#### Clone from GitHub

**Linux/macOS:**
```bash
# Clone the repository
git clone https://github.com/limingda1212/ProxyPool.git
cd ProxyPool

# Create a virtual environment (optional)
python3 -m venv venv
source venv/bin/activate  # Linux/macOS
# or venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt
```

**Windows:**
```
# Use PowerShell or CMD
git clone https://github.com/limingda1212/ProxyPool.git
cd ProxyPool

# Create a virtual environment (optional)
python -m venv venv
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Running
```bash
# Run the main program
python main.py
# or
python3 main.py
```

The project comes with necessary configuration files and database.

---

### ☁️ Cloud Deployment

To automate proxy pool maintenance, it is recommended to deploy the GitHub Actions:

#### Deployment Steps

1.  **Create a new GitHub repository** (public recommended for unlimited runtime)
    ```bash
    # Create a new directory locally
    mkdir Proxy-Pool-Actions
    cd Proxy-Pool-Actions
    
    # Copy cloud deployment files
    cp -r ../ProxyPool/cloud_deployment/* .
    
    # Initialize Git repository
    git init
    git add .
    git commit -m "Initial commit: Proxy Pool Actions"
    ```

2.  **Push to GitHub**
    ```bash
    # Add remote repository (replace with your repository URL)
    git remote add origin https://github.com/YourUsername/YourRepositoryName.git
    git branch -M main
    git push -u origin main
    ```

3.  **Configure GitHub Token and Repository**
    -   Create a Personal Access Token on GitHub (requires `repo` scope).
    -   Add the token in the settings menu of the local program.
    -   Modify the repository address in the local program's settings menu.

### GitHub Actions Workflows
-   **🕐 Crawl New Proxies**: Runs daily between 10:00-12:00 Beijing Time.
-   **🔄 Update Existing Proxies**: Runs daily between 13:00-15:00 Beijing Time.

![Actions Status](https://github.com/LiMingda-101212/Proxy-Pool-Actions/actions/workflows/Crawl-and-verify-new-proxies.yml/badge.svg)
![Actions Status](https://github.com/LiMingda-101212/Proxy-Pool-Actions/actions/workflows/Update-existing-proxies.yml/badge.svg)

---

### 📖 User Guide

#### Main Menu Functions

1.  **🔍 Load and Validate New Proxies**
    -   Import from web crawlers or local files.
    -   Automatic deduplication and format checking.
    -   Supports specifying proxy type or automatic detection.
    -   Transparent proxy detection.

2.  **🔄 Validate Proxies in the Pool**
    -   Update the status of existing proxies.
    -   Dynamically adjust scores (+ for success, - for failure).
    -   Interruption recovery feature.

3.  **🌐 Browser Usability Validation**
    -   Test in a real browser environment using Playwright.
    -   Detect browser compatibility issues.

4.  **🛡️ Proxy Security Validation**
    -   DNS hijacking detection.
    -   SSL certificate validation.
    -   Malicious content detection.

5.  **📤 Extract Proxies**
    -   Extract a specified number of proxies based on requirements.
    -   Supports filtering by: type, region, score, security.
    -   Intelligent load balancing.

6.  **📊 View Proxy Pool Status**
    -   Real-time statistics.
    -   Score distribution chart.
    -   Regional distribution analysis.

7.  **☁️ Synchronize with Cloud Proxy Pool**
    -   Merge local and cloud proxy pools.
    -   Automatic format conversion.

8.  **🔧 API Service**
    -   Start/stop the API server.
    -   Supports multiple retrieval methods.
    -   Proxy status management (idle/busy/dead).

9.  **⚙️ Settings**
    -   Modify configuration file.
    -   Set GitHub Token.
    -   Adjust validation parameters.

**Note: The synchronization feature between local and cloud requires a token. Please add it in the settings menu.**

---

## 3. Code Introduction

### 🎯 Cloud Code (actions_main.py)

`Automated proxy management via GitHub Actions`

Responsible for interfacing with the developer's local proxy pool. Due to the long execution time of Actions, it is recommended to place it in a [public repository <click here to see the cloud repository used by this project>](https://github.com/LiMingda-101212/Proxy-Pool-Actions).

#### Workflows

1.  Crawl and validate new proxies, runs daily between 10:00-12:00 Beijing Time - UTC+2.
2.  Re-validate existing proxies, runs daily between 13:00-15:00 Beijing Time - UTC+5.

#### Current Actions Status

Crawl and validate new proxies
![Proxy Pool Update](https://github.com/LiMingda-101212/Proxy-Pool-Actions/actions/workflows/Crawl-and-verify-new-proxies.yml/badge.svg)

Re-validate existing proxies
![Proxy Pool Update](https://github.com/LiMingda-101212/Proxy-Pool-Actions/actions/workflows/Update-existing-proxies.yml/badge.svg)

### 🎯 Developer Local Main Code

`Automated proxy management`

Implements relatively comprehensive functions:
-   1.  **Load and Validate New Proxies**: Load from crawlers (automatic crawling, optionally specify type) or local files (for manual addition, can choose type for speed or use slower auto-detection). Adds passing proxies to the pool. New proxies use auto-detected or specified type. Deduplication and invalid proxy filtering before validation to avoid wasted effort. Maximum score 100; new proxies passing either domestic or international 204 service get 98 points; invalid/error proxies get 0. Supports transparent proxy detection to identify IP-leaking proxies. Includes interruption recovery: if validation is interrupted, completed proxies are saved, incomplete ones are saved to an interrupt file for later resumption. Can fetch proxy info (city, ISP, etc.), skipping already known IPs.
-   2.  **Check and Update Existing Proxies**: Uses the type saved in the database for validation, checks domestic and international support. Successful validation for one (domestic/international) adds +1 point, success for both adds +2; invalid/error proxies lose 1 point, providing a clearer view of stability. Supports transparent proxy detection.
-   3.  **Browser Usability Validation**: Detects proxies usable in a real browser environment using Playwright.
-   4.  **Proxy Security Validation**: Checks proxy security.
-   5.  **Extract Proxies**: Extracts specified number of proxies, prioritizing high-score, stable ones. Allows filtering by type, supported region, transparency, and browser usability.
-   6.  **View Proxy Pool Status**: Shows total count, score distribution by type, supported regions, browser usability statistics, etc.
-   7.  **Merge with GitHub Actions Maintained Pool**: Merges the locally maintained pool with the one on GitHub, converting the simplified cloud format to the detailed local format.
-   8.  **API Service**: Provides start and debug functions. Uses proxy statuses (`idle`, `busy`, `dead`) to prevent the same proxy from being used concurrently by different crawlers.
-   9.  **Manually Clean 0-Score Proxies** from the database.
-   10. **Settings Menu**: Avoids manual editing of `config.json`.
-   11. **Help Menu**: Provides help information.

### 🎯 Proxy Pool

Introduction to the Cloud Proxy Pool File (proxies.csv) - Stores basic info, portable cloud version:

```
Type,Proxy:Port,Score,China,International,Transparent,DetectedIP

💭 Detailed Description:
Type -> Proxy type, supports http/socks
Proxy:Port -> Proxy address and port
Score -> Score (0-100), reflects stability
China -> Supports China (True/False), validated using a Chinese website (currently Baidu)
International -> Supports International (True/False), validated using an international website (currently Google)
Transparent -> Is it a transparent proxy (True/False), compared against the machine's real IP
DetectedIP -> Detected IP address, can be unknown/ip/dict (sometimes detailed)
```

Introduction to the Developer's Local Proxy Pool Database (SQLite: proxies.db) - Comprehensive information:

```
proxies table:
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        proxy TEXT UNIQUE NOT NULL,
        score INTEGER DEFAULT 50,
        types TEXT,  -- JSON array string ["http", "socks5"]
        support_china BOOLEAN DEFAULT 0,
        support_international BOOLEAN DEFAULT 0,
        transparent BOOLEAN DEFAULT 0,
        detected_ip TEXT,
        city TEXT,
        region TEXT,
        country TEXT,
        loc TEXT,
        org TEXT,
        postal TEXT,
        timezone TEXT,
        browser_valid BOOLEAN DEFAULT 0,
        browser_check_date TEXT,
        browser_response_time REAL DEFAULT -1,
        dns_hijacking TEXT,
        ssl_valid TEXT,
        malicious_content TEXT,
        data_integrity TEXT
        behavior_analysis TEXT
        security_check_date TEXT,
        avg_response_time REAL DEFAULT 0,
        success_rate REAL DEFAULT 0.0,
        last_checked TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

proxy_status table:
        proxy TEXT PRIMARY KEY,
        status TEXT DEFAULT 'idle',  -- idle, busy, dead
        task_id TEXT,
        acquire_time REAL,
        heartbeat_time REAL,
        FOREIGN KEY (proxy) REFERENCES proxies(proxy) ON DELETE CASCADE

proxy_usage table:
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        proxy TEXT,
        task_id TEXT,
        start_time REAL,
        end_time REAL,
        success BOOLEAN,
        response_time REAL,
        score_change INTEGER,
        FOREIGN KEY (proxy) REFERENCES proxies(proxy) ON DELETE CASCADE
```

---

## 📈 4. Updates

### (Main Code main.py)

```
<V1.0.0> Dec 14, 2025 : ✅ Implemented:
    ✳️1. Load and validate new proxies from web crawlers or local files. Added to pool after validation. Deduplication.
    Score 98 for passing 204 check. Supports transparent proxy detection. Interruption recovery. Fetches IP info.
    ✳️2. Check and update existing proxies using saved types. Score adjustments (+1/+2/-1). Transparent proxy detection. Interruption recovery.
    ✳️3. Browser usability validation with Playwright. Interruption recovery.
    ✳️4. Proxy security validation - Development started V1.0.0, implemented V2.2.0.
    ✳️5. Extract proxies with filtering by type, region, transparency, browser usability.
    ✳️6. View proxy pool status.
    ✳️7. Merge with GitHub Actions maintained pool.
    ✳️8. Settings menu.
    ✳️9. Help menu.
    This version's main code proxy pool format: proxy, score, proxy_info_dict
<V1.1.0> Dec 20, 2025 : Refactored to standard proxy pool, added API entry, multiple URLs for different purposes. Added proxy statuses (idle/busy/dead).
<V1.2.0> Dec 21, 2025 : Migrated proxy pool to SQLite, refactored code around database.
<V2.0.0> Jan 11, 2026 : Split monolithic main file into multiple modules.
<V2.1.0> Feb 12, 2026 : Changed validation services to international and domestic 204 services.
<V2.1.1> Feb 13, 2026 : Project renamed to ProxyPool, versioning switched to standard X.Y.Z format.
<V2.2.0> Feb 21, 2026 : Completed proxy security validation, added missing DB columns, security validation functional. Added security filter to extraction. Added security stats to status view. Optimized DB code.
```

### (Cloud Code actions_main.py)

Implements basic crawling, validation, and re-validation functions.

```
<V1.0.0 Adaptation> Dec 14, 2025 : Written based on main code. Crawling/validation and re-validation split into two workflows.
    Cloud code format: Type,Proxy,Score,China,International,Transparent,DetectedIP
<V2.1.0 Adaptation> Feb 12, 2026 : Changed validation services to international and domestic 204 services.
```

---

## 5. Notes

---

### 📞 Support & Feedback

-   📧 Issues: GitHub Issues
-   💬 Discussions: GitHub Discussions
-   ⭐ If you like this project, please give it a `Star`!

---

### 🔒 Disclaimer

Regarding the Crawler Functionality

**Important Notice:**

The crawler functionality in this project is intended for learning and research purposes only. Users should:

-   **Comply with Laws and Regulations**: Ensure the crawler is used within legal boundaries.
-   **Respect Website Rules**: Adhere to the target website's `robots.txt` protocol and terms of service.
-   **Control Request Frequency**: Avoid placing excessive load on target websites.
-   **Define Purpose of Use**: Must not be used for illegal or unethical activities.

**Developer's Statement**

The developer of this project is not responsible for:

-   User violations of laws or regulations while using this project.
-   User infringement upon third-party rights.
-   Any losses or legal issues arising from the use of proxies.

**Suggestions and Warnings**

🔸 Only use publicly available proxy sources.

🔸 Do not crawl copyrighted content.

🔸 Avoid crawling personal private information.

🔸 It is recommended to obtain website permission before crawling.

**Users assume all risks associated with using this project.**

---

### 🙏 Acknowledgements

Thanks to all open-source project contributors, especially:

-   [requests](https://github.com/psf/requests) - HTTP library
-   [aiohttp](https://github.com/aio-libs/aiohttp) - Asynchronous HTTP library
-   [playwright-python](https://github.com/microsoft/playwright-python) - Browser automation

---

### 📄 Open Source License

This project is licensed under the GNU General Public License v3.0 (GPL v3).

Key Terms:

-   **Free Use**: You may freely use, copy, and distribute this project.
-   **Open Source Requirement**: Modifications to this project must be released under the same license.
-   **Disclaimer of Warranty**: This project is provided "AS IS", without any warranty.
-   For the full license text, please see the [LICENSE](LICENSE) file.

---
