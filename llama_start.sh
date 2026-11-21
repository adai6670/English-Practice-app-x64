#!/bin/bash
./llama--ubuntu-vulkan-x64/llama-server -m ./models/gemma-4-E2B_q4_0-it.gguf -ngl -1 -fa on -t 2 -cmoe -c 32768 --host 0.0.0.0 --port 8080 --temp 0.7
