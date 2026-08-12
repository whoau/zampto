name: Zampto Auto Renew

on:
  schedule:
    # 每天 UTC 0:00（北京时间 8:00）运行，可根据需要调整 cron 表达式
    - cron: '0 0 * * *'
  workflow_dispatch:  # 允许手动触发

jobs:
  renew:
    runs-on: ubuntu-latest

    steps:
      # 1. 检出代码仓库
      - name: Checkout code
        uses: actions/checkout@v4

      # 2. 设置 Python 环境
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.10'

      # 3. 安装系统依赖（Chrome 浏览器、虚拟显示服务）
      - name: Install system dependencies
        run: |
          sudo apt-get update
          sudo apt-get install -y \
            xvfb \
            xdotool \
            wget \
            unzip \
            chromium-browser \
            chromium-chromedriver
          # 设置环境变量，让 Selenium 能找到 Chrome
          echo "CHROME_PATH=/usr/bin/chromium-browser" >> $GITHUB_ENV
          echo "CHROMEDRIVER_PATH=/usr/bin/chromedriver" >> $GITHUB_ENV

      # 4. 安装 Python 依赖
      - name: Install Python dependencies
        run: |
          python -m pip install --upgrade pip
          if [ -f requirements.txt ]; then pip install -r requirements.txt; fi

      # 5. 运行续期脚本（带代理配置）
      - name: Run renew script
        env:
          # 从 GitHub Secrets 注入敏感信息
          ZAM_PTO_EMAIL: ${{ secrets.ZAM_PTO_EMAIL }}
          ZAM_PTO_PASSWORD: ${{ secrets.ZAM_PTO_PASSWORD }}
          TG_CHAT_ID: ${{ secrets.TG_CHAT_ID }}
          TG_BOT_TOKEN: ${{ secrets.TG_BOT_TOKEN }}
          # 代理节点配置（必填，因为 zampto 需要代理访问）
          IS_PROXY: ${{ secrets.IS_PROXY }}
          PROXY_SERVER: ${{ secrets.PROXY_SERVER }}
        run: |
          # 使用 xvfb-run 创建虚拟显示，以支持无头浏览器运行
          xvfb-run python main.py
