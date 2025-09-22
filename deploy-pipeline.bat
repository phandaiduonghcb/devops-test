@echo off
echo Deploying Pipeline Stack...

set ENV=dev
if not "%1"=="" set ENV=%1

echo.
echo Environment: %ENV%
echo Stack: DevOpsApp-Pipeline-%ENV%
echo.

cd cdk
cdk deploy DevOpsApp-Pipeline-%ENV% --context env=%ENV% --require-approval never

if %errorlevel% equ 0 (
    echo.
    echo ✅ Pipeline deployed successfully!
    echo 📋 Pipeline: devops-app-%ENV%
    echo 🌿 Branch: %BRANCH%
    echo 📦 ECR: devops-app-%ENV%
) else (
    echo.
    echo ❌ Pipeline deployment failed!
)

pause