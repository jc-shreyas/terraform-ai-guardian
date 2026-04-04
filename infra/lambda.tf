resource "aws_lambda_function" "processor" {
  function_name = "${var.project_name}-processor"
  runtime       = "python3.8"
  handler       = "main.handler"
  filename      = "lambda.zip"

  memory_size = 10240
  timeout     = 900

  environment {
    variables = {
      DB_HOST     = aws_db_instance.main.endpoint
      DB_PASSWORD = "ProductionPass45678!"
      API_KEY     = "sk-live-abc123xyz789"
    }
  }

  # Missing: role argument (required)
  # Missing: source_code_hash
}
