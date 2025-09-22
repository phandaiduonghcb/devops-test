@echo off
echo Deploying Infrastructure Stack...

set ENV=dev
if not "%1"=="" set ENV=%1

echo.
echo Environment: %ENV%
echo Stack: DevOpsApp-Infrastructure-%ENV%
echo.

cd cdk
cdk deploy DevOpsApp-Infrastructure-%ENV% --context env=%ENV% --require-approval never

if %errorlevel% equ 0 (
    echo.
    echo ✅ Infrastructure deployed successfully!
    echo 🏗️ ECS Cluster: devops-app-cluster-%ENV%
    echo 🚀 ECS Service: devops-app-service-%ENV%
    echo 🌐 VPC: devops-app-vpc-%ENV%
) else (
    echo.
    echo ❌ Infrastructure deployment failed!
)

pause