datacenter = "dc1"
node_name = "consul-server"

server = true
bootstrap_expect = 1

data_dir = "/consul/data"
bind_addr = "0.0.0.0"
client_addr = "0.0.0.0"

ui_config {
  enabled = true
}

acl {
  enabled = true
  default_policy = "allow"
  enable_token_persistence = true
}