output "cluster_name" {
  value = module.eks.cluster_name
}

output "ecr_registry" {
  value = "${data.aws_caller_identity.current.account_id}.dkr.ecr.${var.aws_region}.amazonaws.com"
}

output "ecr_repository_urls" {
  value = { for name, repo in aws_ecr_repository.service : name => repo.repository_url }
}

output "ecr_repository_names" {
  value = { for name, repo in aws_ecr_repository.service : name => repo.name }
}

output "load_balancer_controller_role_arn" {
  value = aws_iam_role.load_balancer_controller.arn
}

output "station_reservation_role_arn" {
  value = aws_iam_role.station_reservation.arn
}

output "saga_orchestrator_role_arn" {
  value = aws_iam_role.saga_orchestrator.arn
}

output "saga_auditor_role_arn" {
  value = aws_iam_role.saga_auditor.arn
}

output "vpc_id" {
  value = module.vpc.vpc_id
}
