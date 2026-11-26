variable "aws_region" {
  description = "AWS region shared by EKS, ECR and the ALB."
  type        = string
}

variable "kubernetes_version" {
  description = "EKS Kubernetes control-plane version."
  type        = string
  default     = "1.33"
}

variable "vpc_cidr" {
  description = "CIDR block for the environment VPC."
  type        = string
  default     = "10.40.0.0/16"
}

variable "cluster_endpoint_public_access_cidrs" {
  description = "Trusted CIDRs allowed to reach the EKS public API endpoint."
  type        = list(string)

  validation {
    condition = (
      length(var.cluster_endpoint_public_access_cidrs) > 0 &&
      alltrue([
        for cidr in var.cluster_endpoint_public_access_cidrs :
        can(cidrhost(cidr, 0)) &&
        cidr != "0.0.0.0/0" &&
        cidr != "::/0"
      ])
    )
    error_message = "Set one or more valid trusted CIDRs; unrestricted IPv4 and IPv6 ranges are not allowed."
  }
}

variable "node_instance_types" {
  description = "EC2 instance types for the managed EKS node group."
  type        = list(string)
  default     = ["t3.medium"]
}

variable "node_desired_size" {
  type    = number
  default = 2
}

variable "node_min_size" {
  type    = number
  default = 2
}

variable "node_max_size" {
  type    = number
  default = 5
}
