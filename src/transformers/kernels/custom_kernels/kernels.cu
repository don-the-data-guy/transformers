#include <torch/extension.h>
#include <ATen/ATen.h>
#include <cuda_runtime.h>
#include <vector>

// example of index_max_kernel
__global__ void index_max_cuda_kernel(
    const float* index_vals,
    const int* indices,
    int A_num_block,
    int B_num_block,
    float* output) {

    
    int idx = blockIdx.x * blockDim.x + threadIdx.x;

    // For simplicity, an example where it performs element-wise max
    if (idx < A_num_block * B_num_block) {
        output[idx] = max(index_vals[idx], (float)indices[idx]);
    }
}

// host function that wraps the kernel
at::Tensor index_max_kernel(
    at::Tensor index_vals,
    at::Tensor indices,
    int A_num_block,
    int B_num_block) {

    // allocate output tensor
    auto output = at::zeros({A_num_block, B_num_block}, index_vals.options());

 
    int threads = 1024;
    int blocks = (A_num_block * B_num_block + threads - 1) / threads;
    index_max_cuda_kernel<<<blocks, threads>>>(
        index_vals.data_ptr<float>(),
        indices.data_ptr<int>(),
        A_num_block,
        B_num_block,
        output.data_ptr<float>());

    return output;
}
