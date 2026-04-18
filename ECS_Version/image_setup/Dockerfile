FROM public.ecr.aws/amazonlinux/amazonlinux:2023-minimal

# Install unzip 
RUN microdnf install -y unzip && microdnf clean all

# Install AWS CLI v2 
RUN curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip" && \
    unzip awscliv2.zip && \
    ./aws/install && \
    rm -rf awscliv2.zip ./aws

# Install Terraform
ENV TF_VERSION=1.8.0
RUN curl -LO "https://releases.hashicorp.com/terraform/${TF_VERSION}/terraform_${TF_VERSION}_linux_amd64.zip" && \
    unzip "terraform_${TF_VERSION}_linux_amd64.zip" && \
    mv terraform /usr/local/bin/ && \
    rm "terraform_${TF_VERSION}_linux_amd64.zip"

# uploading the entrypoint script
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# Adding user for least privalege execution
RUN useradd -m infrascope
USER infrascope
WORKDIR /home/infrascope

# Set the entrypoint to the script
# This means that when the container starts, the first processes that the kernel will execute is the script.
# The script acts as the heart of the container, so when the script exists, the container will stop
# This script will be responsible for pulling the code, unzipping it, and executing, according to the command
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]