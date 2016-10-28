#!/bin/bash

g++ -o bh_tsne -std=c++11 -O2 tsne.cpp sptree.cpp || exit 1

neighbours_file=$1

tmp_inp_file=$(mktemp)

n=$(cat "$neighbours_file" | wc -l)
dims=0
theta=0.3
perplexity=50
no_dims=2
max_iter=1000

printf "%d %d %f %d %d %d\n" "$n" "$dims" "$theta" "$perplexity" "$no_dims" "$max_iter" > "$tmp_inp_file"
cat "$neighbours_file" >> "$tmp_inp_file"

./bh_tsne < "$tmp_inp_file"
