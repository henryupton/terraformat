resource "terraform_data" "keep" { input = "b" }
resource "terraform_data" "new_name" { input = "m" }
moved {
  from = terraform_data.old_name
  to   = terraform_data.new_name
}
removed {
  from = terraform_data.forget_me
  lifecycle { destroy = false }
}
resource "terraform_data" "swap" {
  input            = "s"
  triggers_replace = ["2"]
}
resource "terraform_data" "fresh" { input = "n" }
