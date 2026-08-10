; ModuleID = 'research/msl/r100c_rpg8_pf1c.metal'
source_filename = "research/msl/r100c_rpg8_pf1c.metal"
target datalayout = "e-p:64:64:64-i1:8:8-i8:8:8-i16:16:16-i32:32:32-i64:64:64-f32:32:32-f64:64:64-v16:16:16-v24:32:32-v32:32:32-v48:64:64-v64:64:64-v96:128:128-v128:128:128-v192:256:256-v256:256:256-v512:512:512-v1024:1024:1024-n8:16:32"
target triple = "air64_v28-apple-macosx26.0.0"

@_ZZ68custom_kernel_laguna_residual_rms_router_bf16_2048_rpg8_keys_v1_pf1cPU9MTLdeviceKDF16bS0_S0_S0_S0_PU9MTLdeviceDF16bS2_S2_PU9MTLdevicejDv3_jS5_jjE14local_inv_mean.0 = internal unnamed_addr addrspace(3) global float undef, align 4
@_ZZ68custom_kernel_laguna_residual_rms_router_bf16_2048_rpg8_keys_v1_pf1cPU9MTLdeviceKDF16bS0_S0_S0_S0_PU9MTLdeviceDF16bS2_S2_PU9MTLdevicejDv3_jS5_jjE10local_sums = internal unnamed_addr addrspace(3) global [32 x float] undef, align 4
@_ZZ68custom_kernel_laguna_residual_rms_router_bf16_2048_rpg8_keys_v1_pf1cPU9MTLdeviceKDF16bS0_S0_S0_S0_PU9MTLdeviceDF16bS2_S2_PU9MTLdevicejDv3_jS5_jjE14normalized_row = internal unnamed_addr addrspace(3) global [2048 x bfloat] undef, align 2

; Function Attrs: convergent mustprogress nounwind
define void @custom_kernel_laguna_residual_rms_router_bf16_2048_rpg8_keys_v1_pf1c(bfloat addrspace(1)* nocapture noundef readonly "air-buffer-no-alias" %0, bfloat addrspace(1)* nocapture noundef readonly "air-buffer-no-alias" %1, bfloat addrspace(1)* nocapture noundef readonly "air-buffer-no-alias" %2, bfloat addrspace(1)* nocapture noundef readonly "air-buffer-no-alias" %3, bfloat addrspace(1)* nocapture noundef readonly "air-buffer-no-alias" %4, bfloat addrspace(1)* nocapture noundef writeonly "air-buffer-no-alias" %5, bfloat addrspace(1)* nocapture noundef writeonly "air-buffer-no-alias" %6, bfloat addrspace(1)* nocapture noundef writeonly "air-buffer-no-alias" %7, i32 addrspace(1)* nocapture noundef writeonly "air-buffer-no-alias" %8, <3 x i32> noundef %9, <3 x i32> noundef %10, i32 noundef %11, i32 noundef %12) local_unnamed_addr #0 {
  %14 = alloca [4 x bfloat], align 2
  %15 = alloca [4 x <4 x bfloat>], align 8
  %16 = alloca [4 x <4 x bfloat>], align 8
  %17 = extractelement <3 x i32> %9, i64 0
  %18 = extractelement <3 x i32> %10, i64 0
  %19 = shl i32 %18, 2
  %20 = bitcast [4 x bfloat]* %14 to i8*
  call void @llvm.lifetime.start.p0i8(i64 8, i8* nonnull %20) #4
  %21 = icmp eq i32 %17, 0
  br label %25

22:                                               ; preds = %39
  %23 = tail call fast float @air.simd_sum.f32(float %42) #5
  %24 = icmp eq i32 %12, 0
  br i1 %24, label %45, label %48

25:                                               ; preds = %13, %39
  %26 = phi float [ 0.000000e+00, %13 ], [ %42, %39 ]
  %27 = phi i32 [ 0, %13 ], [ %43, %39 ]
  %28 = add nuw nsw i32 %27, %19
  %29 = zext i32 %28 to i64
  %30 = getelementptr inbounds bfloat, bfloat addrspace(1)* %0, i64 %29
  %31 = load bfloat, bfloat addrspace(1)* %30, align 2, !tbaa !32, !alias.scope !36, !noalias !39
  %32 = getelementptr inbounds bfloat, bfloat addrspace(1)* %1, i64 %29
  %33 = load bfloat, bfloat addrspace(1)* %32, align 2, !tbaa !32, !alias.scope !48, !noalias !49
  %34 = fadd fast bfloat %33, %31
  %35 = zext i32 %27 to i64
  %36 = getelementptr inbounds [4 x bfloat], [4 x bfloat]* %14, i64 0, i64 %35
  store bfloat %34, bfloat* %36, align 2, !tbaa !32
  br i1 %21, label %37, label %39

37:                                               ; preds = %25
  %38 = getelementptr inbounds bfloat, bfloat addrspace(1)* %5, i64 %29
  store bfloat %34, bfloat addrspace(1)* %38, align 2, !tbaa !32, !alias.scope !50, !noalias !51
  br label %39

39:                                               ; preds = %37, %25
  %40 = fpext bfloat %34 to float
  %41 = fmul fast float %40, %40
  %42 = fadd fast float %41, %26
  %43 = add nuw nsw i32 %27, 1
  %44 = icmp eq i32 %43, 4
  br i1 %44, label %22, label %25, !llvm.loop !52

45:                                               ; preds = %22
  %46 = zext i32 %11 to i64
  %47 = getelementptr inbounds [32 x float], [32 x float] addrspace(3)* @_ZZ68custom_kernel_laguna_residual_rms_router_bf16_2048_rpg8_keys_v1_pf1cPU9MTLdeviceKDF16bS0_S0_S0_S0_PU9MTLdeviceDF16bS2_S2_PU9MTLdevicejDv3_jS5_jjE10local_sums, i64 0, i64 %46
  store float 0.000000e+00, float addrspace(3)* %47, align 4, !tbaa !54
  br label %48

48:                                               ; preds = %45, %22
  tail call void @air.wg.barrier(i32 2, i32 1) #5
  %49 = icmp eq i32 %11, 0
  br i1 %49, label %50, label %53

50:                                               ; preds = %48
  %51 = zext i32 %12 to i64
  %52 = getelementptr inbounds [32 x float], [32 x float] addrspace(3)* @_ZZ68custom_kernel_laguna_residual_rms_router_bf16_2048_rpg8_keys_v1_pf1cPU9MTLdeviceKDF16bS0_S0_S0_S0_PU9MTLdeviceDF16bS2_S2_PU9MTLdevicejDv3_jS5_jjE10local_sums, i64 0, i64 %51
  store float %23, float addrspace(3)* %52, align 4, !tbaa !54
  br label %53

53:                                               ; preds = %50, %48
  tail call void @air.wg.barrier(i32 2, i32 1) #5
  br i1 %24, label %54, label %63

54:                                               ; preds = %53
  %55 = zext i32 %11 to i64
  %56 = getelementptr inbounds [32 x float], [32 x float] addrspace(3)* @_ZZ68custom_kernel_laguna_residual_rms_router_bf16_2048_rpg8_keys_v1_pf1cPU9MTLdeviceKDF16bS0_S0_S0_S0_PU9MTLdeviceDF16bS2_S2_PU9MTLdevicejDv3_jS5_jjE10local_sums, i64 0, i64 %55
  %57 = load float, float addrspace(3)* %56, align 4, !tbaa !54
  %58 = tail call fast float @air.simd_sum.f32(float %57) #5
  br i1 %49, label %59, label %63

59:                                               ; preds = %54
  %60 = fmul fast float %58, 0x3F40000000000000
  %61 = fadd fast float %60, 0x3EB0C6F7A0000000
  %62 = tail call fast float @air.rsqrt.f32(float %61) #6
  store float %62, float addrspace(3)* @_ZZ68custom_kernel_laguna_residual_rms_router_bf16_2048_rpg8_keys_v1_pf1cPU9MTLdeviceKDF16bS0_S0_S0_S0_PU9MTLdeviceDF16bS2_S2_PU9MTLdevicejDv3_jS5_jjE14local_inv_mean.0, align 4, !tbaa !54
  br label %63

63:                                               ; preds = %54, %59, %53
  tail call void @air.wg.barrier(i32 2, i32 1) #5
  %64 = load float, float addrspace(3)* @_ZZ68custom_kernel_laguna_residual_rms_router_bf16_2048_rpg8_keys_v1_pf1cPU9MTLdeviceKDF16bS0_S0_S0_S0_PU9MTLdeviceDF16bS2_S2_PU9MTLdevicejDv3_jS5_jjE14local_inv_mean.0, align 4, !tbaa !54
  br label %68

65:                                               ; preds = %84
  tail call void @air.wg.barrier(i32 2, i32 1) #5
  %66 = bitcast [4 x <4 x bfloat>]* %15 to i8*
  call void @llvm.lifetime.start.p0i8(i64 32, i8* nonnull %66) #4
  %67 = icmp ult i32 %12, 8
  br i1 %67, label %87, label %218

68:                                               ; preds = %63, %84
  %69 = phi i32 [ 0, %63 ], [ %85, %84 ]
  %70 = add nuw nsw i32 %69, %19
  %71 = zext i32 %70 to i64
  %72 = getelementptr inbounds bfloat, bfloat addrspace(1)* %2, i64 %71
  %73 = load bfloat, bfloat addrspace(1)* %72, align 2, !tbaa !32, !alias.scope !56, !noalias !57
  %74 = zext i32 %69 to i64
  %75 = getelementptr inbounds [4 x bfloat], [4 x bfloat]* %14, i64 0, i64 %74
  %76 = load bfloat, bfloat* %75, align 2, !tbaa !32
  %77 = fpext bfloat %76 to float
  %78 = fmul fast float %64, %77
  %79 = fptrunc float %78 to bfloat
  %80 = fmul fast bfloat %73, %79
  %81 = getelementptr inbounds [2048 x bfloat], [2048 x bfloat] addrspace(3)* @_ZZ68custom_kernel_laguna_residual_rms_router_bf16_2048_rpg8_keys_v1_pf1cPU9MTLdeviceKDF16bS0_S0_S0_S0_PU9MTLdeviceDF16bS2_S2_PU9MTLdevicejDv3_jS5_jjE14normalized_row, i64 0, i64 %71
  store bfloat %80, bfloat addrspace(3)* %81, align 2, !tbaa !32
  br i1 %21, label %82, label %84

82:                                               ; preds = %68
  %83 = getelementptr inbounds bfloat, bfloat addrspace(1)* %6, i64 %71
  store bfloat %80, bfloat addrspace(1)* %83, align 2, !tbaa !32, !alias.scope !58, !noalias !59
  br label %84

84:                                               ; preds = %82, %68
  %85 = add nuw nsw i32 %69, 1
  %86 = icmp eq i32 %85, 4
  br i1 %86, label %65, label %68, !llvm.loop !60

87:                                               ; preds = %65
  %88 = shl i32 %17, 3
  %89 = add nuw i32 %88, %12
  %90 = shl i32 %11, 2
  %91 = shl i32 %89, 11
  %92 = zext i32 %91 to i64
  %93 = getelementptr inbounds bfloat, bfloat addrspace(1)* %3, i64 %92
  %94 = zext i32 %90 to i64
  %95 = getelementptr inbounds bfloat, bfloat addrspace(1)* %93, i64 %94
  br label %96

96:                                               ; preds = %87, %96
  %97 = phi i32 [ 0, %87 ], [ %105, %96 ]
  %98 = shl nuw nsw i32 %97, 7
  %99 = zext i32 %98 to i64
  %100 = getelementptr inbounds bfloat, bfloat addrspace(1)* %95, i64 %99
  %101 = bitcast bfloat addrspace(1)* %100 to <4 x bfloat> addrspace(1)*
  %102 = load <4 x bfloat>, <4 x bfloat> addrspace(1)* %101, align 8, !tbaa !61, !alias.scope !62, !noalias !63
  %103 = zext i32 %97 to i64
  %104 = getelementptr inbounds [4 x <4 x bfloat>], [4 x <4 x bfloat>]* %15, i64 0, i64 %103
  store <4 x bfloat> %102, <4 x bfloat>* %104, align 8, !tbaa !61
  %105 = add nuw nsw i32 %97, 1
  %106 = icmp eq i32 %105, 4
  br i1 %106, label %109, label %96, !llvm.loop !64

107:                                              ; preds = %117
  %108 = bitcast [4 x <4 x bfloat>]* %16 to i8*
  br label %134

109:                                              ; preds = %96, %117
  %110 = phi i32 [ %118, %117 ], [ 0, %96 ]
  %111 = phi float [ %131, %117 ], [ 0.000000e+00, %96 ]
  %112 = shl nuw nsw i32 %110, 7
  %113 = add i32 %112, %90
  %114 = zext i32 %110 to i64
  %115 = getelementptr inbounds [4 x <4 x bfloat>], [4 x <4 x bfloat>]* %15, i64 0, i64 %114
  %116 = load <4 x bfloat>, <4 x bfloat>* %115, align 8, !tbaa !61
  br label %120

117:                                              ; preds = %120
  %118 = add nuw nsw i32 %110, 1
  %119 = icmp eq i32 %118, 4
  br i1 %119, label %107, label %109, !llvm.loop !65

120:                                              ; preds = %109, %120
  %121 = phi i32 [ 0, %109 ], [ %132, %120 ]
  %122 = phi float [ %111, %109 ], [ %131, %120 ]
  %123 = extractelement <4 x bfloat> %116, i32 %121
  %124 = fpext bfloat %123 to float
  %125 = add i32 %113, %121
  %126 = zext i32 %125 to i64
  %127 = getelementptr inbounds [2048 x bfloat], [2048 x bfloat] addrspace(3)* @_ZZ68custom_kernel_laguna_residual_rms_router_bf16_2048_rpg8_keys_v1_pf1cPU9MTLdeviceKDF16bS0_S0_S0_S0_PU9MTLdeviceDF16bS2_S2_PU9MTLdevicejDv3_jS5_jjE14normalized_row, i64 0, i64 %126
  %128 = load bfloat, bfloat addrspace(3)* %127, align 2, !tbaa !32
  %129 = fpext bfloat %128 to float
  %130 = fmul fast float %129, %124
  %131 = fadd fast float %130, %122
  %132 = add nuw nsw i32 %121, 1
  %133 = icmp eq i32 %132, 4
  br i1 %133, label %117, label %120, !llvm.loop !66

134:                                              ; preds = %107, %152
  %135 = phi i32 [ %90, %107 ], [ %138, %152 ]
  %136 = phi i32 [ 4, %107 ], [ %153, %152 ]
  %137 = phi float [ %131, %107 ], [ %177, %152 ]
  %138 = add i32 %135, 512
  call void @llvm.lifetime.start.p0i8(i64 32, i8* nonnull %108) #4
  %139 = zext i32 %138 to i64
  %140 = getelementptr inbounds bfloat, bfloat addrspace(1)* %93, i64 %139
  br label %141

141:                                              ; preds = %134, %141
  %142 = phi i32 [ 0, %134 ], [ %150, %141 ]
  %143 = shl nuw nsw i32 %142, 7
  %144 = zext i32 %143 to i64
  %145 = getelementptr inbounds bfloat, bfloat addrspace(1)* %140, i64 %144
  %146 = bitcast bfloat addrspace(1)* %145 to <4 x bfloat> addrspace(1)*
  %147 = load <4 x bfloat>, <4 x bfloat> addrspace(1)* %146, align 8, !tbaa !61, !alias.scope !62, !noalias !63
  %148 = zext i32 %142 to i64
  %149 = getelementptr inbounds [4 x <4 x bfloat>], [4 x <4 x bfloat>]* %16, i64 0, i64 %148
  store <4 x bfloat> %147, <4 x bfloat>* %149, align 8, !tbaa !61
  %150 = add nuw nsw i32 %142, 1
  %151 = icmp eq i32 %150, 4
  br i1 %151, label %155, label %141, !llvm.loop !67

152:                                              ; preds = %163
  call void @llvm.lifetime.end.p0i8(i64 32, i8* nonnull %108) #4
  %153 = add nuw nsw i32 %136, 4
  %154 = icmp ult i32 %136, 12
  br i1 %154, label %134, label %181, !llvm.loop !68

155:                                              ; preds = %141, %163
  %156 = phi i32 [ %164, %163 ], [ 0, %141 ]
  %157 = phi float [ %177, %163 ], [ %137, %141 ]
  %158 = shl nuw nsw i32 %156, 7
  %159 = add i32 %158, %138
  %160 = zext i32 %156 to i64
  %161 = getelementptr inbounds [4 x <4 x bfloat>], [4 x <4 x bfloat>]* %16, i64 0, i64 %160
  %162 = load <4 x bfloat>, <4 x bfloat>* %161, align 8, !tbaa !61
  br label %166

163:                                              ; preds = %166
  %164 = add nuw nsw i32 %156, 1
  %165 = icmp eq i32 %164, 4
  br i1 %165, label %152, label %155, !llvm.loop !69

166:                                              ; preds = %155, %166
  %167 = phi i32 [ 0, %155 ], [ %178, %166 ]
  %168 = phi float [ %157, %155 ], [ %177, %166 ]
  %169 = extractelement <4 x bfloat> %162, i32 %167
  %170 = fpext bfloat %169 to float
  %171 = add i32 %159, %167
  %172 = zext i32 %171 to i64
  %173 = getelementptr inbounds [2048 x bfloat], [2048 x bfloat] addrspace(3)* @_ZZ68custom_kernel_laguna_residual_rms_router_bf16_2048_rpg8_keys_v1_pf1cPU9MTLdeviceKDF16bS0_S0_S0_S0_PU9MTLdeviceDF16bS2_S2_PU9MTLdevicejDv3_jS5_jjE14normalized_row, i64 0, i64 %172
  %174 = load bfloat, bfloat addrspace(3)* %173, align 2, !tbaa !32
  %175 = fpext bfloat %174 to float
  %176 = fmul fast float %175, %170
  %177 = fadd fast float %176, %168
  %178 = add nuw nsw i32 %167, 1
  %179 = icmp eq i32 %178, 4
  br i1 %179, label %163, label %166, !llvm.loop !70

180:                                              ; preds = %181
  br i1 %49, label %189, label %218

181:                                              ; preds = %152, %181
  %182 = phi i16 [ %187, %181 ], [ 16, %152 ]
  %183 = phi float [ %186, %181 ], [ %177, %152 ]
  %184 = freeze float %183
  %185 = tail call fast float @air.simd_shuffle_down.f32(float %184, i16 %182) #5
  %186 = fadd fast float %184, %185
  %187 = lshr i16 %182, 1
  %188 = icmp ult i16 %182, 2
  br i1 %188, label %180, label %181, !llvm.loop !71

189:                                              ; preds = %180
  %190 = fptrunc float %186 to bfloat
  %191 = zext i32 %89 to i64
  %192 = getelementptr inbounds bfloat, bfloat addrspace(1)* %7, i64 %191
  store bfloat %190, bfloat addrspace(1)* %192, align 2, !tbaa !32, !alias.scope !72, !noalias !73
  %193 = fpext bfloat %190 to float
  %194 = tail call fast float @air.fast_fabs.f32(float %193) #6
  %195 = tail call fast float @air.fast_exp.f32(float %194) #6
  %196 = fadd fast float %195, 1.000000e+00
  %197 = fdiv fast float 1.000000e+00, %196
  %198 = fcmp fast olt bfloat %190, 0xR0000
  %199 = fsub fast float 1.000000e+00, %197
  %200 = select fast i1 %198, float %197, float %199
  %201 = getelementptr inbounds bfloat, bfloat addrspace(1)* %4, i64 %191
  %202 = load bfloat, bfloat addrspace(1)* %201, align 2, !tbaa !32, !alias.scope !74, !noalias !75
  %203 = fpext bfloat %202 to float
  %204 = fadd fast float %200, %203
  %205 = fneg fast float %204
  %206 = bitcast float %205 to i32
  %207 = and i32 %206, 2147483647
  %208 = icmp ugt i32 %207, 2139095040
  br i1 %208, label %215, label %209

209:                                              ; preds = %189
  %210 = icmp eq i32 %207, 0
  %211 = icmp sgt i32 %206, -1
  %212 = select i1 %211, i32 -2147483648, i32 -1
  %213 = xor i32 %212, %206
  %214 = select i1 %210, i32 -2147483648, i32 %213
  br label %215

215:                                              ; preds = %209, %189
  %216 = phi i32 [ -1, %189 ], [ %214, %209 ]
  %217 = getelementptr inbounds i32, i32 addrspace(1)* %8, i64 %191
  store i32 %216, i32 addrspace(1)* %217, align 4, !tbaa !76, !alias.scope !78, !noalias !79
  br label %218

218:                                              ; preds = %180, %215, %65
  call void @llvm.lifetime.end.p0i8(i64 32, i8* nonnull %66) #4
  call void @llvm.lifetime.end.p0i8(i64 8, i8* nonnull %20) #4
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
!9 = !{void (bfloat addrspace(1)*, bfloat addrspace(1)*, bfloat addrspace(1)*, bfloat addrspace(1)*, bfloat addrspace(1)*, bfloat addrspace(1)*, bfloat addrspace(1)*, bfloat addrspace(1)*, i32 addrspace(1)*, <3 x i32>, <3 x i32>, i32, i32)* @custom_kernel_laguna_residual_rms_router_bf16_2048_rpg8_keys_v1_pf1c, !10, !11}
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
!31 = !{!"/Users/ec2-user/.senpai/native/mlxfast-maple-20260804/roles/student-maple-frieren/workspace/target/research/msl/r100c_rpg8_pf1c.metal"}
!32 = !{!33, !33, i64 0}
!33 = !{!"bfloat", !34, i64 0}
!34 = !{!"omnipotent char", !35, i64 0}
!35 = !{!"Simple C++ TBAA"}
!36 = !{!37}
!37 = distinct !{!37, !38, !"air-alias-scope-arg(0)"}
!38 = distinct !{!38, !"air-alias-scopes(custom_kernel_laguna_residual_rms_router_bf16_2048_rpg8_keys_v1_pf1c)"}
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
!69 = distinct !{!69, !53}
!70 = distinct !{!70, !53}
!71 = distinct !{!71, !53}
!72 = !{!46}
!73 = !{!37, !40, !41, !42, !43, !44, !45, !47}
!74 = !{!43}
!75 = !{!37, !40, !41, !42, !44, !45, !46, !47}
!76 = !{!77, !77, i64 0}
!77 = !{!"int", !34, i64 0}
!78 = !{!47}
!79 = !{!37, !40, !41, !42, !43, !44, !45, !46}
