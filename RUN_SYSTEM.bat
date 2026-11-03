@echo off
cd /d "%~dp0"
echo =====================================
echo  BATTERY PREDICTIVE MAINTENANCE
echo =====================================
echo.
python -c "import streamlit, plotly, sklearn" 2>nul
if errorlevel 1 (
    echo Installing required packages, please wait...
    python -m pip install -r requirements.txt
)
python -m streamlit run app.py
pause
