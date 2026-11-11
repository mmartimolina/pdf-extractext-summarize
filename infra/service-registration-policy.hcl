node_prefix "consul-server" {
  policy = "write"
}

service "pdf-extract" {
  policy = "write"
}

service "pdf-validation" {
  policy = "write"
}

service "pdf-summarize" {
  policy = "write"
}

service "pdf-persistence" {
  policy = "write"
}
