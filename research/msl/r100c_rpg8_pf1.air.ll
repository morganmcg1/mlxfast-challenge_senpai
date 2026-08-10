; ModuleID = 'research/msl/r100c_rpg8_pf1.metal'
source_filename = "research/msl/r100c_rpg8_pf1.metal"
target datalayout = "e-p:64:64:64-i1:8:8-i8:8:8-i16:16:16-i32:32:32-i64:64:64-f32:32:32-f64:64:64-v16:16:16-v24:32:32-v32:32:32-v48:64:64-v64:64:64-v96:128:128-v128:128:128-v192:256:256-v256:256:256-v512:512:512-v1024:1024:1024-n8:16:32"
target triple = "air64_v28-apple-macosx26.0.0"

@_ZZ67custom_kernel_laguna_residual_rms_router_bf16_2048_rpg8_keys_v1_pf1PU9MTLdeviceKDF16bS0_S0_S0_S0_PU9MTLdeviceDF16bS2_S2_PU9MTLdevicejDv3_jS5_jjE14local_inv_mean.0 = internal unnamed_addr addrspace(3) global float undef, align 4
@_ZZ67custom_kernel_laguna_residual_rms_router_bf16_2048_rpg8_keys_v1_pf1PU9MTLdeviceKDF16bS0_S0_S0_S0_PU9MTLdeviceDF16bS2_S2_PU9MTLdevicejDv3_jS5_jjE10local_sums = internal unnamed_addr addrspace(3) global [32 x float] undef, align 4
@_ZZ67custom_kernel_laguna_residual_rms_router_bf16_2048_rpg8_keys_v1_pf1PU9MTLdeviceKDF16bS0_S0_S0_S0_PU9MTLdeviceDF16bS2_S2_PU9MTLdevicejDv3_jS5_jjE14normalized_row = internal unnamed_addr addrspace(3) global [2048 x bfloat] undef, align 2

; Function Attrs: convergent mustprogress nounwind
define void @custom_kernel_laguna_residual_rms_router_bf16_2048_rpg8_keys_v1_pf1(bfloat addrspace(1)* nocapture noundef readonly "air-buffer-no-alias" %0, bfloat addrspace(1)* nocapture noundef readonly "air-buffer-no-alias" %1, bfloat addrspace(1)* nocapture noundef readonly "air-buffer-no-alias" %2, bfloat addrspace(1)* nocapture noundef readonly "air-buffer-no-alias" %3, bfloat addrspace(1)* nocapture noundef readonly "air-buffer-no-alias" %4, bfloat addrspace(1)* nocapture noundef writeonly "air-buffer-no-alias" %5, bfloat addrspace(1)* nocapture noundef writeonly "air-buffer-no-alias" %6, bfloat addrspace(1)* nocapture noundef writeonly "air-buffer-no-alias" %7, i32 addrspace(1)* nocapture noundef writeonly "air-buffer-no-alias" %8, <3 x i32> noundef %9, <3 x i32> noundef %10, i32 noundef %11, i32 noundef %12) local_unnamed_addr #0 {
  %14 = alloca [4 x bfloat], align 2
  %15 = alloca [4 x <4 x bfloat>], align 8
  %16 = alloca [4 x <4 x bfloat>], align 8
  %17 = extractelement <3 x i32> %9, i64 0
  %18 = extractelement <3 x i32> %10, i64 0
  %19 = shl i32 %18, 2
  %20 = bitcast [4 x bfloat]* %14 to i8*
  call void @llvm.lifetime.start.p0i8(i64 8, i8* nonnull %20) #4
  %21 = icmp eq i32 %17, 0
  br label %26

22:                                               ; preds = %40
  %23 = tail call fast float @air.simd_sum.f32(float %43) #5
  %24 = bitcast [4 x <4 x bfloat>]* %15 to i8*
  call void @llvm.lifetime.start.p0i8(i64 32, i8* nonnull %24) #4
  %25 = icmp ult i32 %12, 8
  br i1 %25, label %46, label %66

26:                                               ; preds = %13, %40
  %27 = phi float [ 0.000000e+00, %13 ], [ %43, %40 ]
  %28 = phi i32 [ 0, %13 ], [ %44, %40 ]
  %29 = add nuw nsw i32 %28, %19
  %30 = zext i32 %29 to i64
  %31 = getelementptr inbounds bfloat, bfloat addrspace(1)* %0, i64 %30
  %32 = load bfloat, bfloat addrspace(1)* %31, align 2, !tbaa !32, !alias.scope !36, !noalias !39
  %33 = getelementptr inbounds bfloat, bfloat addrspace(1)* %1, i64 %30
  %34 = load bfloat, bfloat addrspace(1)* %33, align 2, !tbaa !32, !alias.scope !48, !noalias !49
  %35 = fadd fast bfloat %34, %32
  %36 = zext i32 %28 to i64
  %37 = getelementptr inbounds [4 x bfloat], [4 x bfloat]* %14, i64 0, i64 %36
  store bfloat %35, bfloat* %37, align 2, !tbaa !32
  br i1 %21, label %38, label %40

38:                                               ; preds = %26
  %39 = getelementptr inbounds bfloat, bfloat addrspace(1)* %5, i64 %30
  store bfloat %35, bfloat addrspace(1)* %39, align 2, !tbaa !32, !alias.scope !50, !noalias !51
  br label %40

40:                                               ; preds = %38, %26
  %41 = fpext bfloat %35 to float
  %42 = fmul fast float %41, %41
  %43 = fadd fast float %42, %27
  %44 = add nuw nsw i32 %28, 1
  %45 = icmp eq i32 %44, 4
  br i1 %45, label %22, label %26, !llvm.loop !52

46:                                               ; preds = %22
  %47 = shl i32 %17, 3
  %48 = add nuw i32 %47, %12
  %49 = shl i32 %11, 2
  %50 = shl i32 %48, 11
  %51 = zext i32 %50 to i64
  %52 = getelementptr inbounds bfloat, bfloat addrspace(1)* %3, i64 %51
  %53 = zext i32 %49 to i64
  %54 = getelementptr inbounds bfloat, bfloat addrspace(1)* %52, i64 %53
  br label %55

55:                                               ; preds = %46, %55
  %56 = phi i32 [ 0, %46 ], [ %64, %55 ]
  %57 = shl nuw nsw i32 %56, 7
  %58 = zext i32 %57 to i64
  %59 = getelementptr inbounds bfloat, bfloat addrspace(1)* %54, i64 %58
  %60 = bitcast bfloat addrspace(1)* %59 to <4 x bfloat> addrspace(1)*
  %61 = load <4 x bfloat>, <4 x bfloat> addrspace(1)* %60, align 8, !tbaa !54, !alias.scope !55, !noalias !56
  %62 = zext i32 %56 to i64
  %63 = getelementptr inbounds [4 x <4 x bfloat>], [4 x <4 x bfloat>]* %15, i64 0, i64 %62
  store <4 x bfloat> %61, <4 x bfloat>* %63, align 8, !tbaa !54
  %64 = add nuw nsw i32 %56, 1
  %65 = icmp eq i32 %64, 4
  br i1 %65, label %66, label %55, !llvm.loop !57

66:                                               ; preds = %55, %22
  %67 = icmp eq i32 %12, 0
  br i1 %67, label %68, label %71

68:                                               ; preds = %66
  %69 = zext i32 %11 to i64
  %70 = getelementptr inbounds [32 x float], [32 x float] addrspace(3)* @_ZZ67custom_kernel_laguna_residual_rms_router_bf16_2048_rpg8_keys_v1_pf1PU9MTLdeviceKDF16bS0_S0_S0_S0_PU9MTLdeviceDF16bS2_S2_PU9MTLdevicejDv3_jS5_jjE10local_sums, i64 0, i64 %69
  store float 0.000000e+00, float addrspace(3)* %70, align 4, !tbaa !58
  br label %71

71:                                               ; preds = %68, %66
  tail call void @air.wg.barrier(i32 2, i32 1) #5
  %72 = icmp eq i32 %11, 0
  br i1 %72, label %73, label %76

73:                                               ; preds = %71
  %74 = zext i32 %12 to i64
  %75 = getelementptr inbounds [32 x float], [32 x float] addrspace(3)* @_ZZ67custom_kernel_laguna_residual_rms_router_bf16_2048_rpg8_keys_v1_pf1PU9MTLdeviceKDF16bS0_S0_S0_S0_PU9MTLdeviceDF16bS2_S2_PU9MTLdevicejDv3_jS5_jjE10local_sums, i64 0, i64 %74
  store float %23, float addrspace(3)* %75, align 4, !tbaa !58
  br label %76

76:                                               ; preds = %73, %71
  tail call void @air.wg.barrier(i32 2, i32 1) #5
  br i1 %67, label %77, label %86

77:                                               ; preds = %76
  %78 = zext i32 %11 to i64
  %79 = getelementptr inbounds [32 x float], [32 x float] addrspace(3)* @_ZZ67custom_kernel_laguna_residual_rms_router_bf16_2048_rpg8_keys_v1_pf1PU9MTLdeviceKDF16bS0_S0_S0_S0_PU9MTLdeviceDF16bS2_S2_PU9MTLdevicejDv3_jS5_jjE10local_sums, i64 0, i64 %78
  %80 = load float, float addrspace(3)* %79, align 4, !tbaa !58
  %81 = tail call fast float @air.simd_sum.f32(float %80) #5
  br i1 %72, label %82, label %86

82:                                               ; preds = %77
  %83 = fmul fast float %81, 0x3F40000000000000
  %84 = fadd fast float %83, 0x3EB0C6F7A0000000
  %85 = tail call fast float @air.rsqrt.f32(float %84) #6
  store float %85, float addrspace(3)* @_ZZ67custom_kernel_laguna_residual_rms_router_bf16_2048_rpg8_keys_v1_pf1PU9MTLdeviceKDF16bS0_S0_S0_S0_PU9MTLdeviceDF16bS2_S2_PU9MTLdevicejDv3_jS5_jjE14local_inv_mean.0, align 4, !tbaa !58
  br label %86

86:                                               ; preds = %77, %82, %76
  tail call void @air.wg.barrier(i32 2, i32 1) #5
  %87 = load float, float addrspace(3)* @_ZZ67custom_kernel_laguna_residual_rms_router_bf16_2048_rpg8_keys_v1_pf1PU9MTLdeviceKDF16bS0_S0_S0_S0_PU9MTLdeviceDF16bS2_S2_PU9MTLdevicejDv3_jS5_jjE14local_inv_mean.0, align 4, !tbaa !58
  br label %89

88:                                               ; preds = %105
  tail call void @air.wg.barrier(i32 2, i32 1) #5
  br i1 %25, label %108, label %226

89:                                               ; preds = %86, %105
  %90 = phi i32 [ 0, %86 ], [ %106, %105 ]
  %91 = add nuw nsw i32 %90, %19
  %92 = zext i32 %91 to i64
  %93 = getelementptr inbounds bfloat, bfloat addrspace(1)* %2, i64 %92
  %94 = load bfloat, bfloat addrspace(1)* %93, align 2, !tbaa !32, !alias.scope !60, !noalias !61
  %95 = zext i32 %90 to i64
  %96 = getelementptr inbounds [4 x bfloat], [4 x bfloat]* %14, i64 0, i64 %95
  %97 = load bfloat, bfloat* %96, align 2, !tbaa !32
  %98 = fpext bfloat %97 to float
  %99 = fmul fast float %87, %98
  %100 = fptrunc float %99 to bfloat
  %101 = fmul fast bfloat %94, %100
  %102 = getelementptr inbounds [2048 x bfloat], [2048 x bfloat] addrspace(3)* @_ZZ67custom_kernel_laguna_residual_rms_router_bf16_2048_rpg8_keys_v1_pf1PU9MTLdeviceKDF16bS0_S0_S0_S0_PU9MTLdeviceDF16bS2_S2_PU9MTLdevicejDv3_jS5_jjE14normalized_row, i64 0, i64 %92
  store bfloat %101, bfloat addrspace(3)* %102, align 2, !tbaa !32
  br i1 %21, label %103, label %105

103:                                              ; preds = %89
  %104 = getelementptr inbounds bfloat, bfloat addrspace(1)* %6, i64 %92
  store bfloat %101, bfloat addrspace(1)* %104, align 2, !tbaa !32, !alias.scope !62, !noalias !63
  br label %105

105:                                              ; preds = %103, %89
  %106 = add nuw nsw i32 %90, 1
  %107 = icmp eq i32 %106, 4
  br i1 %107, label %88, label %89, !llvm.loop !64

108:                                              ; preds = %88
  %109 = shl i32 %17, 3
  %110 = shl i32 %11, 2
  br label %117

111:                                              ; preds = %125
  %112 = add nuw i32 %109, %12
  %113 = bitcast [4 x <4 x bfloat>]* %16 to i8*
  %114 = shl i32 %112, 11
  %115 = zext i32 %114 to i64
  %116 = getelementptr inbounds bfloat, bfloat addrspace(1)* %3, i64 %115
  br label %142

117:                                              ; preds = %108, %125
  %118 = phi i32 [ 0, %108 ], [ %126, %125 ]
  %119 = phi float [ 0.000000e+00, %108 ], [ %139, %125 ]
  %120 = shl nuw nsw i32 %118, 7
  %121 = add i32 %120, %110
  %122 = zext i32 %118 to i64
  %123 = getelementptr inbounds [4 x <4 x bfloat>], [4 x <4 x bfloat>]* %15, i64 0, i64 %122
  %124 = load <4 x bfloat>, <4 x bfloat>* %123, align 8, !tbaa !54
  br label %128

125:                                              ; preds = %128
  %126 = add nuw nsw i32 %118, 1
  %127 = icmp eq i32 %126, 4
  br i1 %127, label %111, label %117, !llvm.loop !65

128:                                              ; preds = %117, %128
  %129 = phi i32 [ 0, %117 ], [ %140, %128 ]
  %130 = phi float [ %119, %117 ], [ %139, %128 ]
  %131 = extractelement <4 x bfloat> %124, i32 %129
  %132 = fpext bfloat %131 to float
  %133 = add i32 %121, %129
  %134 = zext i32 %133 to i64
  %135 = getelementptr inbounds [2048 x bfloat], [2048 x bfloat] addrspace(3)* @_ZZ67custom_kernel_laguna_residual_rms_router_bf16_2048_rpg8_keys_v1_pf1PU9MTLdeviceKDF16bS0_S0_S0_S0_PU9MTLdeviceDF16bS2_S2_PU9MTLdevicejDv3_jS5_jjE14normalized_row, i64 0, i64 %134
  %136 = load bfloat, bfloat addrspace(3)* %135, align 2, !tbaa !32
  %137 = fpext bfloat %136 to float
  %138 = fmul fast float %137, %132
  %139 = fadd fast float %138, %130
  %140 = add nuw nsw i32 %129, 1
  %141 = icmp eq i32 %140, 4
  br i1 %141, label %125, label %128, !llvm.loop !66

142:                                              ; preds = %111, %160
  %143 = phi i32 [ %110, %111 ], [ %146, %160 ]
  %144 = phi i32 [ 4, %111 ], [ %161, %160 ]
  %145 = phi float [ %139, %111 ], [ %185, %160 ]
  %146 = add i32 %143, 512
  call void @llvm.lifetime.start.p0i8(i64 32, i8* nonnull %113) #4
  %147 = zext i32 %146 to i64
  %148 = getelementptr inbounds bfloat, bfloat addrspace(1)* %116, i64 %147
  br label %149

149:                                              ; preds = %142, %149
  %150 = phi i32 [ 0, %142 ], [ %158, %149 ]
  %151 = shl nuw nsw i32 %150, 7
  %152 = zext i32 %151 to i64
  %153 = getelementptr inbounds bfloat, bfloat addrspace(1)* %148, i64 %152
  %154 = bitcast bfloat addrspace(1)* %153 to <4 x bfloat> addrspace(1)*
  %155 = load <4 x bfloat>, <4 x bfloat> addrspace(1)* %154, align 8, !tbaa !54, !alias.scope !55, !noalias !56
  %156 = zext i32 %150 to i64
  %157 = getelementptr inbounds [4 x <4 x bfloat>], [4 x <4 x bfloat>]* %16, i64 0, i64 %156
  store <4 x bfloat> %155, <4 x bfloat>* %157, align 8, !tbaa !54
  %158 = add nuw nsw i32 %150, 1
  %159 = icmp eq i32 %158, 4
  br i1 %159, label %163, label %149, !llvm.loop !67

160:                                              ; preds = %171
  call void @llvm.lifetime.end.p0i8(i64 32, i8* nonnull %113) #4
  %161 = add nuw nsw i32 %144, 4
  %162 = icmp ult i32 %144, 12
  br i1 %162, label %142, label %189, !llvm.loop !68

163:                                              ; preds = %149, %171
  %164 = phi i32 [ %172, %171 ], [ 0, %149 ]
  %165 = phi float [ %185, %171 ], [ %145, %149 ]
  %166 = shl nuw nsw i32 %164, 7
  %167 = add i32 %166, %146
  %168 = zext i32 %164 to i64
  %169 = getelementptr inbounds [4 x <4 x bfloat>], [4 x <4 x bfloat>]* %16, i64 0, i64 %168
  %170 = load <4 x bfloat>, <4 x bfloat>* %169, align 8, !tbaa !54
  br label %174

171:                                              ; preds = %174
  %172 = add nuw nsw i32 %164, 1
  %173 = icmp eq i32 %172, 4
  br i1 %173, label %160, label %163, !llvm.loop !69

174:                                              ; preds = %163, %174
  %175 = phi i32 [ 0, %163 ], [ %186, %174 ]
  %176 = phi float [ %165, %163 ], [ %185, %174 ]
  %177 = extractelement <4 x bfloat> %170, i32 %175
  %178 = fpext bfloat %177 to float
  %179 = add i32 %167, %175
  %180 = zext i32 %179 to i64
  %181 = getelementptr inbounds [2048 x bfloat], [2048 x bfloat] addrspace(3)* @_ZZ67custom_kernel_laguna_residual_rms_router_bf16_2048_rpg8_keys_v1_pf1PU9MTLdeviceKDF16bS0_S0_S0_S0_PU9MTLdeviceDF16bS2_S2_PU9MTLdevicejDv3_jS5_jjE14normalized_row, i64 0, i64 %180
  %182 = load bfloat, bfloat addrspace(3)* %181, align 2, !tbaa !32
  %183 = fpext bfloat %182 to float
  %184 = fmul fast float %183, %178
  %185 = fadd fast float %184, %176
  %186 = add nuw nsw i32 %175, 1
  %187 = icmp eq i32 %186, 4
  br i1 %187, label %171, label %174, !llvm.loop !70

188:                                              ; preds = %189
  br i1 %72, label %197, label %226

189:                                              ; preds = %160, %189
  %190 = phi i16 [ %195, %189 ], [ 16, %160 ]
  %191 = phi float [ %194, %189 ], [ %185, %160 ]
  %192 = freeze float %191
  %193 = tail call fast float @air.simd_shuffle_down.f32(float %192, i16 %190) #5
  %194 = fadd fast float %192, %193
  %195 = lshr i16 %190, 1
  %196 = icmp ult i16 %190, 2
  br i1 %196, label %188, label %189, !llvm.loop !71

197:                                              ; preds = %188
  %198 = fptrunc float %194 to bfloat
  %199 = zext i32 %112 to i64
  %200 = getelementptr inbounds bfloat, bfloat addrspace(1)* %7, i64 %199
  store bfloat %198, bfloat addrspace(1)* %200, align 2, !tbaa !32, !alias.scope !72, !noalias !73
  %201 = fpext bfloat %198 to float
  %202 = tail call fast float @air.fast_fabs.f32(float %201) #6
  %203 = tail call fast float @air.fast_exp.f32(float %202) #6
  %204 = fadd fast float %203, 1.000000e+00
  %205 = fdiv fast float 1.000000e+00, %204
  %206 = fcmp fast olt bfloat %198, 0xR0000
  %207 = fsub fast float 1.000000e+00, %205
  %208 = select fast i1 %206, float %205, float %207
  %209 = getelementptr inbounds bfloat, bfloat addrspace(1)* %4, i64 %199
  %210 = load bfloat, bfloat addrspace(1)* %209, align 2, !tbaa !32, !alias.scope !74, !noalias !75
  %211 = fpext bfloat %210 to float
  %212 = fadd fast float %208, %211
  %213 = fneg fast float %212
  %214 = bitcast float %213 to i32
  %215 = and i32 %214, 2147483647
  %216 = icmp ugt i32 %215, 2139095040
  br i1 %216, label %223, label %217

217:                                              ; preds = %197
  %218 = icmp eq i32 %215, 0
  %219 = icmp sgt i32 %214, -1
  %220 = select i1 %219, i32 -2147483648, i32 -1
  %221 = xor i32 %220, %214
  %222 = select i1 %218, i32 -2147483648, i32 %221
  br label %223

223:                                              ; preds = %217, %197
  %224 = phi i32 [ -1, %197 ], [ %222, %217 ]
  %225 = getelementptr inbounds i32, i32 addrspace(1)* %8, i64 %199
  store i32 %224, i32 addrspace(1)* %225, align 4, !tbaa !76, !alias.scope !78, !noalias !79
  br label %226

226:                                              ; preds = %188, %223, %88
  call void @llvm.lifetime.end.p0i8(i64 32, i8* nonnull %24) #4
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
!9 = !{void (bfloat addrspace(1)*, bfloat addrspace(1)*, bfloat addrspace(1)*, bfloat addrspace(1)*, bfloat addrspace(1)*, bfloat addrspace(1)*, bfloat addrspace(1)*, bfloat addrspace(1)*, i32 addrspace(1)*, <3 x i32>, <3 x i32>, i32, i32)* @custom_kernel_laguna_residual_rms_router_bf16_2048_rpg8_keys_v1_pf1, !10, !11}
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
!31 = !{!"/Users/ec2-user/.senpai/native/mlxfast-maple-20260804/roles/student-maple-frieren/workspace/target/research/msl/r100c_rpg8_pf1.metal"}
!32 = !{!33, !33, i64 0}
!33 = !{!"bfloat", !34, i64 0}
!34 = !{!"omnipotent char", !35, i64 0}
!35 = !{!"Simple C++ TBAA"}
!36 = !{!37}
!37 = distinct !{!37, !38, !"air-alias-scope-arg(0)"}
!38 = distinct !{!38, !"air-alias-scopes(custom_kernel_laguna_residual_rms_router_bf16_2048_rpg8_keys_v1_pf1)"}
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
!54 = !{!34, !34, i64 0}
!55 = !{!42}
!56 = !{!37, !40, !41, !43, !44, !45, !46, !47}
!57 = distinct !{!57, !53}
!58 = !{!59, !59, i64 0}
!59 = !{!"float", !34, i64 0}
!60 = !{!41}
!61 = !{!37, !40, !42, !43, !44, !45, !46, !47}
!62 = !{!45}
!63 = !{!37, !40, !41, !42, !43, !44, !46, !47}
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
