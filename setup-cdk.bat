@echo off
echo Setting up CDK Pipeline...

echo.
echo 1. Installing CDK dependencies...
cd cdk
pip install -r requirements.txt

echo.
echo 2. Checking AWS CLI configuration...
aws sts get-caller-identity

echo.
echo 3. Checking CDK CLI...
cdk --version

echo.
echo 4. Setup complete!
echo.
echo Next steps:
echo 1. Update GitHub repo info in cdk/stacks/pipeline_stack.py
echo 2. Update environment config in cdk/configs/environments.json  
echo 3. Create GitHub token secret: aws secretsmanager create-secret --name github-token --secret-string "your-token"
echo 4. Deploy: python cdk/deploy.py dev [account-id] [region]

pause