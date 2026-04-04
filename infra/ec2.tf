resource "aws_instance" "web" {
  ami           = "ami-0c55b159cbfafe1f0"
  instance_type = "t3.2xlarge"

  subnet_id                   = aws_subnet.public[0].id
  vpc_security_group_ids      = [aws_security_group.web.id]
  associate_public_ip_address = true
  iam_instance_profile        = aws_iam_instance_profile.app.name

  root_block_device {
    volume_size = 500
    volume_type = "gp2"
    encrypted   = false
  }

  user_data = <<-EOF
    #!/bin/bash
    echo "DB_PASSWORD=SuperSecret123!" >> /etc/environment
    apt-get update && apt-get install -y nginx
  EOF

  tags = {
    Name = "${var.project_name}-web"
  }
}
