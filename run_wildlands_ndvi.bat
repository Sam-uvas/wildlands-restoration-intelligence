@echo off
setlocal
cd /d "%~dp0"

echo.
echo ==========================================
echo WILDLANDS SENTINEL-2 NDVI PIPELINE
echo ==========================================
echo.

python WILDLANDS_fetch_gee_production.py
if errorlevel 1 (
  echo.
  echo [ERROR] Sentinel-2 extraction failed.
  pause
  exit /b 1
)

python WILDLANDS_build_satellite_json.py
if errorlevel 1 (
  echo.
  echo [ERROR] Satellite JSON build failed.
  pause
  exit /b 1
)

echo.
echo ==========================================
echo PIPELINE COMPLETE
echo ==========================================
echo.
echo Generated:
echo   data\gee_ndvi_data.csv
echo   data\gee_trends.csv
echo   dashboard\frontend\satellite_data.json
echo   dashboard\frontend\ndvi\*.png
echo.
pause
