@echo off
echo Setting up Python virtual environment for CDK...

REM Create virtual environment
python -m venv cdk-env

REM Activate virtual environment
call cdk-env\Scripts\activate.bat

REM Upgrade pip
python -m pip install --upgrade pip

REM Install CDK CLI globally (if not already installed)
npm install -g aws-cdk

REM Install Python dependencies for CDK
cd cdk
pip install -r requirements.txt
cd ..

echo.
echo Virtual environment setup completed!
echo.
echo To activate the environment, run:
echo   call cdk-env\Scripts\activate.bat
echo.
echo To deactivate, run:
echo   deactivate