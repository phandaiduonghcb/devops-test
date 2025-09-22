@echo off
echo Setting up GitHub Token for CodePipeline...

echo.
echo 1. Go to GitHub Settings > Developer settings > Personal access tokens > Tokens (classic)
echo 2. Generate new token with these permissions:
echo    - repo (Full control of private repositories)
echo    - admin:repo_hook (Full control of repository hooks)
echo.
echo 3. Copy the token and run this command:
echo    aws secretsmanager create-secret --name github-token --secret-string "your-github-token-here"
echo.
echo 4. Or update existing secret:
echo    aws secretsmanager update-secret --secret-id github-token --secret-string "your-github-token-here"
echo.

set /p token="Enter your GitHub token (or press Enter to skip): "
if "%token%"=="" (
    echo Skipped token setup. You can set it up later.
    goto :end
)

echo Setting up GitHub token in AWS Secrets Manager...
aws secretsmanager create-secret --name github-token --secret-string "%token%" 2>nul
if %errorlevel% neq 0 (
    echo Token already exists, updating...
    aws secretsmanager update-secret --secret-id github-token --secret-string "%token%"
)

echo.
echo ✅ GitHub token configured successfully!

:end
pause