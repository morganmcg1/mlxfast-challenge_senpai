; ModuleID = 'research/msl/r100c_rpg8_pf0.metal'
source_filename = "research/msl/r100c_rpg8_pf0.metal"
target datalayout = "e-p:64:64:64-i1:8:8-i8:8:8-i16:16:16-i32:32:32-i64:64:64-f32:32:32-f64:64:64-v16:16:16-v24:32:32-v32:32:32-v48:64:64-v64:64:64-v96:128:128-v128:128:128-v192:256:256-v256:256:256-v512:512:512-v1024:1024:1024-n8:16:32"
target triple = "air64_v28-apple-macosx26.0.0"

@_ZZ67custom_kernel_laguna_residual_rms_router_bf16_2048_rpg8_keys_v1_pf0PU9MTLdeviceKDF16bS0_S0_S0_S0_PU9MTLdeviceDF16bS2_S2_PU9MTLdevicejDv3_jS5_jjE14local_inv_mean.0 = internal unnamed_addr addrspace(3) global float undef, align 4
@_ZZ67custom_kernel_laguna_residual_rms_router_bf16_2048_rpg8_keys_v1_pf0PU9MTLdeviceKDF16bS0_S0_S0_S0_PU9MTLdeviceDF16bS2_S2_PU9MTLdevicejDv3_jS5_jjE10local_sums = internal unnamed_addr addrspace(3) global [32 x float] undef, align 4
@_ZZ67custom_kernel_laguna_residual_rms_router_bf16_2048_rpg8_keys_v1_pf0PU9MTLdeviceKDF16bS0_S0_S0_S0_PU9MTLdeviceDF16bS2_S2_PU9MTLdevicejDv3_jS5_jjE14normalized_row = internal unnamed_addr addrspace(3) global [2048 x bfloat] undef, align 2

; Function Attrs: convergent mustprogress nounwind
define void @custom_kernel_laguna_residual_rms_router_bf16_2048_rpg8_keys_v1_pf0(bfloat addrspace(1)* nocapture noundef readonly "air-buffer-no-alias" %0, bfloat addrspace(1)* nocapture noundef readonly "air-buffer-no-alias" %1, bfloat addrspace(1)* nocapture noundef readonly "air-buffer-no-alias" %2, bfloat addrspace(1)* nocapture noundef readonly "air-buffer-no-alias" %3, bfloat addrspace(1)* nocapture noundef readonly "air-buffer-no-alias" %4, bfloat addrspace(1)* nocapture noundef writeonly "air-buffer-no-alias" %5, bfloat addrspace(1)* nocapture noundef writeonly "air-buffer-no-alias" %6, bfloat addrspace(1)* nocapture noundef writeonly "air-buffer-no-alias" %7, i32 addrspace(1)* nocapture noundef writeonly "air-buffer-no-alias" %8, <3 x i32> noundef %9, <3 x i32> noundef %10, i32 noundef %11, i32 noundef %12) local_unnamed_addr #0 {
  %14 = alloca [4 x bfloat], align 2
  %15 = alloca [4 x <4 x bfloat>], align 8
  %16 = extractelement <3 x i32> %9, i64 0
  %17 = extractelement <3 x i32> %10, i64 0
  %18 = shl i32 %17, 2
  %19 = bitcast [4 x bfloat]* %14 to i8*
  call void @llvm.lifetime.start.p0i8(i64 8, i8* nonnull %19) #4
  %20 = icmp eq i32 %16, 0
  br label %24

21:                                               ; preds = %38
  %22 = tail call fast float @air.simd_sum.f32(float %41) #5
  %23 = icmp eq i32 %12, 0
  br i1 %23, label %44, label %47

24:                                               ; preds = %13, %38
  %25 = phi float [ 0.000000e+00, %13 ], [ %41, %38 ]
  %26 = phi i32 [ 0, %13 ], [ %42, %38 ]
  %27 = add nuw nsw i32 %26, %18
  %28 = zext i32 %27 to i64
  %29 = getelementptr inbounds bfloat, bfloat addrspace(1)* %0, i64 %28
  %30 = load bfloat, bfloat addrspace(1)* %29, align 2, !tbaa !32, !alias.scope !36, !noalias !39
  %31 = getelementptr inbounds bfloat, bfloat addrspace(1)* %1, i64 %28
  %32 = load bfloat, bfloat addrspace(1)* %31, align 2, !tbaa !32, !alias.scope !48, !noalias !49
  %33 = fadd fast bfloat %32, %30
  %34 = zext i32 %26 to i64
  %35 = getelementptr inbounds [4 x bfloat], [4 x bfloat]* %14, i64 0, i64 %34
  store bfloat %33, bfloat* %35, align 2, !tbaa !32
  br i1 %20, label %36, label %38

36:                                               ; preds = %24
  %37 = getelementptr inbounds bfloat, bfloat addrspace(1)* %5, i64 %28
  store bfloat %33, bfloat addrspace(1)* %37, align 2, !tbaa !32, !alias.scope !50, !noalias !51
  br label %38

38:                                               ; preds = %36, %24
  %39 = fpext bfloat %33 to float
  %40 = fmul fast float %39, %39
  %41 = fadd fast float %40, %25
  %42 = add nuw nsw i32 %26, 1
  %43 = icmp eq i32 %42, 4
  br i1 %43, label %21, label %24, !llvm.loop !52

44:                                               ; preds = %21
  %45 = zext i32 %11 to i64
  %46 = getelementptr inbounds [32 x float], [32 x float] addrspace(3)* @_ZZ67custom_kernel_laguna_residual_rms_router_bf16_2048_rpg8_keys_v1_pf0PU9MTLdeviceKDF16bS0_S0_S0_S0_PU9MTLdeviceDF16bS2_S2_PU9MTLdevicejDv3_jS5_jjE10local_sums, i64 0, i64 %45
  store float 0.000000e+00, float addrspace(3)* %46, align 4, !tbaa !54
  br label %47

47:                                               ; preds = %44, %21
  tail call void @air.wg.barrier(i32 2, i32 1) #5
  %48 = icmp eq i32 %11, 0
  br i1 %48, label %49, label %52

49:                                               ; preds = %47
  %50 = zext i32 %12 to i64
  %51 = getelementptr inbounds [32 x float], [32 x float] addrspace(3)* @_ZZ67custom_kernel_laguna_residual_rms_router_bf16_2048_rpg8_keys_v1_pf0PU9MTLdeviceKDF16bS0_S0_S0_S0_PU9MTLdeviceDF16bS2_S2_PU9MTLdevicejDv3_jS5_jjE10local_sums, i64 0, i64 %50
  store float %22, float addrspace(3)* %51, align 4, !tbaa !54
  br label %52

52:                                               ; preds = %49, %47
  tail call void @air.wg.barrier(i32 2, i32 1) #5
  br i1 %23, label %53, label %62

53:                                               ; preds = %52
  %54 = zext i32 %11 to i64
  %55 = getelementptr inbounds [32 x float], [32 x float] addrspace(3)* @_ZZ67custom_kernel_laguna_residual_rms_router_bf16_2048_rpg8_keys_v1_pf0PU9MTLdeviceKDF16bS0_S0_S0_S0_PU9MTLdeviceDF16bS2_S2_PU9MTLdevicejDv3_jS5_jjE10local_sums, i64 0, i64 %54
  %56 = load float, float addrspace(3)* %55, align 4, !tbaa !54
  %57 = tail call fast float @air.simd_sum.f32(float %56) #5
  br i1 %48, label %58, label %62

58:                                               ; preds = %53
  %59 = fmul fast float %57, 0x3F40000000000000
  %60 = fadd fast float %59, 0x3EB0C6F7A0000000
  %61 = tail call fast float @air.rsqrt.f32(float %60) #6
  store float %61, float addrspace(3)* @_ZZ67custom_kernel_laguna_residual_rms_router_bf16_2048_rpg8_keys_v1_pf0PU9MTLdeviceKDF16bS0_S0_S0_S0_PU9MTLdeviceDF16bS2_S2_PU9MTLdevicejDv3_jS5_jjE14local_inv_mean.0, align 4, !tbaa !54
  br label %62

62:                                               ; preds = %53, %58, %52
  tail call void @air.wg.barrier(i32 2, i32 1) #5
  %63 = load float, float addrspace(3)* @_ZZ67custom_kernel_laguna_residual_rms_router_bf16_2048_rpg8_keys_v1_pf0PU9MTLdeviceKDF16bS0_S0_S0_S0_PU9MTLdeviceDF16bS2_S2_PU9MTLdevicejDv3_jS5_jjE14local_inv_mean.0, align 4, !tbaa !54
  br label %66

64:                                               ; preds = %82
  tail call void @air.wg.barrier(i32 2, i32 1) #5
  %65 = icmp ult i32 %12, 8
  br i1 %65, label %85, label %177

66:                                               ; preds = %62, %82
  %67 = phi i32 [ 0, %62 ], [ %83, %82 ]
  %68 = add nuw nsw i32 %67, %18
  %69 = zext i32 %68 to i64
  %70 = getelementptr inbounds bfloat, bfloat addrspace(1)* %2, i64 %69
  %71 = load bfloat, bfloat addrspace(1)* %70, align 2, !tbaa !32, !alias.scope !56, !noalias !57
  %72 = zext i32 %67 to i64
  %73 = getelementptr inbounds [4 x bfloat], [4 x bfloat]* %14, i64 0, i64 %72
  %74 = load bfloat, bfloat* %73, align 2, !tbaa !32
  %75 = fpext bfloat %74 to float
  %76 = fmul fast float %63, %75
  %77 = fptrunc float %76 to bfloat
  %78 = fmul fast bfloat %71, %77
  %79 = getelementptr inbounds [2048 x bfloat], [2048 x bfloat] addrspace(3)* @_ZZ67custom_kernel_laguna_residual_rms_router_bf16_2048_rpg8_keys_v1_pf0PU9MTLdeviceKDF16bS0_S0_S0_S0_PU9MTLdeviceDF16bS2_S2_PU9MTLdevicejDv3_jS5_jjE14normalized_row, i64 0, i64 %69
  store bfloat %78, bfloat addrspace(3)* %79, align 2, !tbaa !32
  br i1 %20, label %80, label %82

80:                                               ; preds = %66
  %81 = getelementptr inbounds bfloat, bfloat addrspace(1)* %6, i64 %69
  store bfloat %78, bfloat addrspace(1)* %81, align 2, !tbaa !32, !alias.scope !58, !noalias !59
  br label %82

82:                                               ; preds = %80, %66
  %83 = add nuw nsw i32 %67, 1
  %84 = icmp eq i32 %83, 4
  br i1 %84, label %64, label %66, !llvm.loop !60

85:                                               ; preds = %64
  %86 = shl i32 %16, 3
  %87 = add nuw i32 %86, %12
  %88 = shl i32 %11, 2
  %89 = bitcast [4 x <4 x bfloat>]* %15 to i8*
  %90 = shl i32 %87, 11
  %91 = zext i32 %90 to i64
  %92 = getelementptr inbounds bfloat, bfloat addrspace(1)* %3, i64 %91
  br label %93

93:                                               ; preds = %85, %110
  %94 = phi i32 [ %88, %85 ], [ %111, %110 ]
  %95 = phi i32 [ 0, %85 ], [ %112, %110 ]
  %96 = phi float [ 0.000000e+00, %85 ], [ %136, %110 ]
  call void @llvm.lifetime.start.p0i8(i64 32, i8* nonnull %89) #4
  %97 = zext i32 %94 to i64
  %98 = getelementptr inbounds bfloat, bfloat addrspace(1)* %92, i64 %97
  br label %99

99:                                               ; preds = %93, %99
  %100 = phi i32 [ 0, %93 ], [ %108, %99 ]
  %101 = shl nuw nsw i32 %100, 7
  %102 = zext i32 %101 to i64
  %103 = getelementptr inbounds bfloat, bfloat addrspace(1)* %98, i64 %102
  %104 = bitcast bfloat addrspace(1)* %103 to <4 x bfloat> addrspace(1)*
  %105 = load <4 x bfloat>, <4 x bfloat> addrspace(1)* %104, align 8, !tbaa !61, !alias.scope !62, !noalias !63
  %106 = zext i32 %100 to i64
  %107 = getelementptr inbounds [4 x <4 x bfloat>], [4 x <4 x bfloat>]* %15, i64 0, i64 %106
  store <4 x bfloat> %105, <4 x bfloat>* %107, align 8, !tbaa !61
  %108 = add nuw nsw i32 %100, 1
  %109 = icmp eq i32 %108, 4
  br i1 %109, label %114, label %99, !llvm.loop !64

110:                                              ; preds = %122
  %111 = add i32 %94, 512
  call void @llvm.lifetime.end.p0i8(i64 32, i8* nonnull %89) #4
  %112 = add nuw nsw i32 %95, 4
  %113 = icmp ult i32 %95, 12
  br i1 %113, label %93, label %140, !llvm.loop !65

114:                                              ; preds = %99, %122
  %115 = phi i32 [ %123, %122 ], [ 0, %99 ]
  %116 = phi float [ %136, %122 ], [ %96, %99 ]
  %117 = shl nuw nsw i32 %115, 7
  %118 = add i32 %117, %94
  %119 = zext i32 %115 to i64
  %120 = getelementptr inbounds [4 x <4 x bfloat>], [4 x <4 x bfloat>]* %15, i64 0, i64 %119
  %121 = load <4 x bfloat>, <4 x bfloat>* %120, align 8, !tbaa !61
  br label %125

122:                                              ; preds = %125
  %123 = add nuw nsw i32 %115, 1
  %124 = icmp eq i32 %123, 4
  br i1 %124, label %110, label %114, !llvm.loop !66

125:                                              ; preds = %114, %125
  %126 = phi i32 [ 0, %114 ], [ %137, %125 ]
  %127 = phi float [ %116, %114 ], [ %136, %125 ]
  %128 = extractelement <4 x bfloat> %121, i32 %126
  %129 = fpext bfloat %128 to float
  %130 = add i32 %118, %126
  %131 = zext i32 %130 to i64
  %132 = getelementptr inbounds [2048 x bfloat], [2048 x bfloat] addrspace(3)* @_ZZ67custom_kernel_laguna_residual_rms_router_bf16_2048_rpg8_keys_v1_pf0PU9MTLdeviceKDF16bS0_S0_S0_S0_PU9MTLdeviceDF16bS2_S2_PU9MTLdevicejDv3_jS5_jjE14normalized_row, i64 0, i64 %131
  %133 = load bfloat, bfloat addrspace(3)* %132, align 2, !tbaa !32
  %134 = fpext bfloat %133 to float
  %135 = fmul fast float %134, %129
  %136 = fadd fast float %135, %127
  %137 = add nuw nsw i32 %126, 1
  %138 = icmp eq i32 %137, 4
  br i1 %138, label %122, label %125, !llvm.loop !67

139:                                              ; preds = %140
  br i1 %48, label %148, label %177

140:                                              ; preds = %110, %140
  %141 = phi i16 [ %146, %140 ], [ 16, %110 ]
  %142 = phi float [ %145, %140 ], [ %136, %110 ]
  %143 = freeze float %142
  %144 = tail call fast float @air.simd_shuffle_down.f32(float %143, i16 %141) #5
  %145 = fadd fast float %143, %144
  %146 = lshr i16 %141, 1
  %147 = icmp ult i16 %141, 2
  br i1 %147, label %139, label %140, !llvm.loop !68

148:                                              ; preds = %139
  %149 = fptrunc float %145 to bfloat
  %150 = zext i32 %87 to i64
  %151 = getelementptr inbounds bfloat, bfloat addrspace(1)* %7, i64 %150
  store bfloat %149, bfloat addrspace(1)* %151, align 2, !tbaa !32, !alias.scope !69, !noalias !70
  %152 = fpext bfloat %149 to float
  %153 = tail call fast float @air.fast_fabs.f32(float %152) #6
  %154 = tail call fast float @air.fast_exp.f32(float %153) #6
  %155 = fadd fast float %154, 1.000000e+00
  %156 = fdiv fast float 1.000000e+00, %155
  %157 = fcmp fast olt bfloat %149, 0xR0000
  %158 = fsub fast float 1.000000e+00, %156
  %159 = select fast i1 %157, float %156, float %158
  %160 = getelementptr inbounds bfloat, bfloat addrspace(1)* %4, i64 %150
  %161 = load bfloat, bfloat addrspace(1)* %160, align 2, !tbaa !32, !alias.scope !71, !noalias !72
  %162 = fpext bfloat %161 to float
  %163 = fadd fast float %159, %162
  %164 = fneg fast float %163
  %165 = bitcast float %164 to i32
  %166 = and i32 %165, 2147483647
  %167 = icmp ugt i32 %166, 2139095040
  br i1 %167, label %174, label %168

168:                                              ; preds = %148
  %169 = icmp eq i32 %166, 0
  %170 = icmp sgt i32 %165, -1
  %171 = select i1 %170, i32 -2147483648, i32 -1
  %172 = xor i32 %171, %165
  %173 = select i1 %169, i32 -2147483648, i32 %172
  br label %174

174:                                              ; preds = %168, %148
  %175 = phi i32 [ -1, %148 ], [ %173, %168 ]
  %176 = getelementptr inbounds i32, i32 addrspace(1)* %8, i64 %150
  store i32 %175, i32 addrspace(1)* %176, align 4, !tbaa !73, !alias.scope !75, !noalias !76
  br label %177

177:                                              ; preds = %139, %174, %64
  call void @llvm.lifetime.end.p0i8(i64 8, i8* nonnull %19) #4
  ret void
}

; Function Attrs: argmemonly mustprogress nocallback nofree nosync nounwind willreturn
declare void @llvm.lifetime.start.p0i8(i64 immarg, i8* nocapture) #1

; Function Attrs: argmemonly mustprogress nocallback nofree nosync nounwind willreturn
declare void @llvm.lifetime.end.p0i8(i64 immarg, i8* nocapture) #1

; Function Attrs: convergent mustprogress nounwind willreturn
declare void @air.wg.barrier(i32, i32) local_unnamed_addr #2

; Function Attrs: mustprogress nofree nosync nounwind readnone willreturn
declare float @air.rsqrt.f32(float) local_unnamed_addr #3

; Function Attrs: mustprogress nofree nosync nounwind readnone willreturn
declare float @air.fast_exp.f32(float) local_unnamed_addr #3

; Function Attrs: mustprogress nofree nosync nounwind readnone willreturn
declare float @air.fast_fabs.f32(float) local_unnamed_addr #3

; Function Attrs: convergent mustprogress nounwind willreturn
declare float @air.simd_sum.f32(float) local_unnamed_addr #2

; Function Attrs: convergent mustprogress nounwind willreturn
declare float @air.simd_shuffle_down.f32(float, i16) local_unnamed_addr #2

attributes #0 = { convergent mustprogress nounwind "approx-func-fp-math"="true" "frame-pointer"="all" "min-legal-vector-width"="96" "no-builtins" "no-infs-fp-math"="true" "no-nans-fp-math"="true" "no-signed-zeros-fp-math"="true" "no-trapping-math"="true" "stack-protector-buffer-size"="8" "unsafe-fp-math"="true" }
attributes #1 = { argmemonly mustprogress nocallback nofree nosync nounwind willreturn }
attributes #2 = { convergent mustprogress nounwind willreturn }
attributes #3 = { mustprogress nofree nosync nounwind readnone willreturn }
attributes #4 = { nounwind }
attributes #5 = { convergent nounwind willreturn }
attributes #6 = { nounwind readnone willreturn }

!llvm.module.flags = !{!0, !1, !2, !3, !4, !5, !6, !7, !8}
!air.kernel = !{!9}
!air.compile_options = !{!25, !26, !27}
!llvm.ident = !{!28}
!air.version = !{!29}
!air.language_version = !{!30}
!air.source_file_name = !{!31}

!0 = !{i32 2, !"SDK Version", [2 x i32] [i32 26, i32 5]}
!1 = !{i32 1, !"wchar_size", i32 4}
!2 = !{i32 7, !"frame-pointer", i32 2}
!3 = !{i32 7, !"air.max_device_buffers", i32 31}
!4 = !{i32 7, !"air.max_constant_buffers", i32 31}
!5 = !{i32 7, !"air.max_threadgroup_buffers", i32 31}
!6 = !{i32 7, !"air.max_textures", i32 128}
!7 = !{i32 7, !"air.max_read_write_textures", i32 8}
!8 = !{i32 7, !"air.max_samplers", i32 16}
!9 = !{void (bfloat addrspace(1)*, bfloat addrspace(1)*, bfloat addrspace(1)*, bfloat addrspace(1)*, bfloat addrspace(1)*, bfloat addrspace(1)*, bfloat addrspace(1)*, bfloat addrspace(1)*, i32 addrspace(1)*, <3 x i32>, <3 x i32>, i32, i32)* @custom_kernel_laguna_residual_rms_router_bf16_2048_rpg8_keys_v1_pf0, !10, !11}
!10 = !{}
!11 = !{!12, !13, !14, !15, !16, !17, !18, !19, !20, !21, !22, !23, !24}
!12 = !{i32 0, !"air.buffer", !"air.location_index", i32 0, i32 1, !"air.read", !"air.address_space", i32 1, !"air.arg_type_size", i32 2, !"air.arg_type_align_size", i32 2, !"air.arg_type_name", !"bfloat", !"air.arg_name", !"residual"}
!13 = !{i32 1, !"air.buffer", !"air.location_index", i32 1, i32 1, !"air.read", !"air.address_space", i32 1, !"air.arg_type_size", i32 2, !"air.arg_type_align_size", i32 2, !"air.arg_type_name", !"bfloat", !"air.arg_name", !"branch"}
!14 = !{i32 2, !"air.buffer", !"air.location_index", i32 2, i32 1, !"air.read", !"air.address_space", i32 1, !"air.arg_type_size", i32 2, !"air.arg_type_align_size", i32 2, !"air.arg_type_name", !"bfloat", !"air.arg_name", !"weight"}
!15 = !{i32 3, !"air.buffer", !"air.location_index", i32 3, i32 1, !"air.read", !"air.address_space", i32 1, !"air.arg_type_size", i32 2, !"air.arg_type_align_size", i32 2, !"air.arg_type_name", !"bfloat", !"air.arg_name", !"router_weight"}
!16 = !{i32 4, !"air.buffer", !"air.location_index", i32 4, i32 1, !"air.read", !"air.address_space", i32 1, !"air.arg_type_size", i32 2, !"air.arg_type_align_size", i32 2, !"air.arg_type_name", !"bfloat", !"air.arg_name", !"correction_bias"}
!17 = !{i32 5, !"air.buffer", !"air.location_index", i32 5, i32 1, !"air.read_write", !"air.address_space", i32 1, !"air.arg_type_size", i32 2, !"air.arg_type_align_size", i32 2, !"air.arg_type_name", !"bfloat", !"air.arg_name", !"summed"}
!18 = !{i32 6, !"air.buffer", !"air.location_index", i32 6, i32 1, !"air.read_write", !"air.address_space", i32 1, !"air.arg_type_size", i32 2, !"air.arg_type_align_size", i32 2, !"air.arg_type_name", !"bfloat", !"air.arg_name", !"normalized"}
!19 = !{i32 7, !"air.buffer", !"air.location_index", i32 7, i32 1, !"air.read_write", !"air.address_space", i32 1, !"air.arg_type_size", i32 2, !"air.arg_type_align_size", i32 2, !"air.arg_type_name", !"bfloat", !"air.arg_name", !"router_logits"}
!20 = !{i32 8, !"air.buffer", !"air.location_index", i32 8, i32 1, !"air.read_write", !"air.address_space", i32 1, !"air.arg_type_size", i32 4, !"air.arg_type_align_size", i32 4, !"air.arg_type_name", !"uint", !"air.arg_name", !"router_keys"}
!21 = !{i32 9, !"air.threadgroup_position_in_grid", !"air.arg_type_name", !"uint3", !"air.arg_name", !"threadgroup_position_in_grid"}
!22 = !{i32 10, !"air.thread_position_in_threadgroup", !"air.arg_type_name", !"uint3", !"air.arg_name", !"thread_position_in_threadgroup"}
!23 = !{i32 11, !"air.thread_index_in_simdgroup", !"air.arg_type_name", !"uint", !"air.arg_name", !"thread_index_in_simdgroup"}
!24 = !{i32 12, !"air.simdgroup_index_in_threadgroup", !"air.arg_type_name", !"uint", !"air.arg_name", !"simdgroup_index_in_threadgroup"}
!25 = !{!"air.compile.denorms_disable"}
!26 = !{!"air.compile.fast_math_enable"}
!27 = !{!"air.compile.framebuffer_fetch_enable"}
!28 = !{!"Apple metal version 32023.883 (metalfe-32023.883)"}
!29 = !{i32 2, i32 8, i32 0}
!30 = !{!"Metal", i32 3, i32 1, i32 0}
!31 = !{!"/Users/ec2-user/.senpai/native/mlxfast-maple-20260804/roles/student-maple-frieren/workspace/target/research/msl/r100c_rpg8_pf0.metal"}
!32 = !{!33, !33, i64 0}
!33 = !{!"bfloat", !34, i64 0}
!34 = !{!"omnipotent char", !35, i64 0}
!35 = !{!"Simple C++ TBAA"}
!36 = !{!37}
!37 = distinct !{!37, !38, !"air-alias-scope-arg(0)"}
!38 = distinct !{!38, !"air-alias-scopes(custom_kernel_laguna_residual_rms_router_bf16_2048_rpg8_keys_v1_pf0)"}
!39 = !{!40, !41, !42, !43, !44, !45, !46, !47}
!40 = distinct !{!40, !38, !"air-alias-scope-arg(1)"}
!41 = distinct !{!41, !38, !"air-alias-scope-arg(2)"}
!42 = distinct !{!42, !38, !"air-alias-scope-arg(3)"}
!43 = distinct !{!43, !38, !"air-alias-scope-arg(4)"}
!44 = distinct !{!44, !38, !"air-alias-scope-arg(5)"}
!45 = distinct !{!45, !38, !"air-alias-scope-arg(6)"}
!46 = distinct !{!46, !38, !"air-alias-scope-arg(7)"}
!47 = distinct !{!47, !38, !"air-alias-scope-arg(8)"}
!48 = !{!40}
!49 = !{!37, !41, !42, !43, !44, !45, !46, !47}
!50 = !{!44}
!51 = !{!37, !40, !41, !42, !43, !45, !46, !47}
!52 = distinct !{!52, !53}
!53 = !{!"llvm.loop.mustprogress"}
!54 = !{!55, !55, i64 0}
!55 = !{!"float", !34, i64 0}
!56 = !{!41}
!57 = !{!37, !40, !42, !43, !44, !45, !46, !47}
!58 = !{!45}
!59 = !{!37, !40, !41, !42, !43, !44, !46, !47}
!60 = distinct !{!60, !53}
!61 = !{!34, !34, i64 0}
!62 = !{!42}
!63 = !{!37, !40, !41, !43, !44, !45, !46, !47}
!64 = distinct !{!64, !53}
!65 = distinct !{!65, !53}
!66 = distinct !{!66, !53}
!67 = distinct !{!67, !53}
!68 = distinct !{!68, !53}
!69 = !{!46}
!70 = !{!37, !40, !41, !42, !43, !44, !45, !47}
!71 = !{!43}
!72 = !{!37, !40, !41, !42, !44, !45, !46, !47}
!73 = !{!74, !74, i64 0}
!74 = !{!"int", !34, i64 0}
!75 = !{!47}
!76 = !{!37, !40, !41, !42, !43, !44, !45, !46}
