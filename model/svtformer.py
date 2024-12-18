## Our model was revised from https://github.com/zczcwh/PoseFormer/blob/main/common/model_poseformer.py

import torch
import torch.nn as nn
from functools import partial
from einops import rearrange
from timm.models.layers import DropPath

from common.opt import opts

opt = opts().parse()
device = torch.device("cuda")


#######################################################################################################################
class Mlp(nn.Module):
    def __init__(self, in_features, hidden_features=None, out_features=None, act_layer=nn.GELU, drop=0.):
        super().__init__()
        out_features = out_features or in_features
        hidden_features = hidden_features or in_features
        self.fc1 = nn.Linear(in_features, hidden_features)
        self.act = act_layer()
        self.fc2 = nn.Linear(hidden_features, out_features)
        self.drop = nn.Dropout(drop)

    def forward(self, x):
        x = self.fc1(x)
        x = self.act(x)
        x = self.drop(x)
        x = self.fc2(x)
        x = self.drop(x)
        return x


#######################################################################################################################
class Attention(nn.Module):
    def __init__(self, dim, num_heads=8, qkv_bias=False, qk_scale=None, attn_drop=0., proj_drop=0.):
        super().__init__()
        self.num_heads = num_heads
        head_dim = dim // num_heads
        self.scale = qk_scale or head_dim ** -0.5

        self.qkv = nn.Linear(dim, dim * 3, bias=qkv_bias)
        self.attn_drop = nn.Dropout(attn_drop)
        self.proj = nn.Linear(dim, dim)
        self.proj_drop = nn.Dropout(proj_drop)

    def forward(self, x):
        B, N, C = x.shape
        qkv = self.qkv(x).reshape(B, N, 3, self.num_heads, C // self.num_heads).permute(2, 0, 3, 1, 4)
        q, k, v = qkv[0], qkv[1], qkv[2]

        attn = (q @ k.transpose(-2, -1)) * self.scale
        attn = attn.softmax(dim=-1)
        attn = self.attn_drop(attn)

        x = (attn @ v).transpose(1, 2).reshape(B, N, C)
        x = self.proj(x)
        x = self.proj_drop(x)
        return x



#######################################################################################################################
class Block(nn.Module):

    def __init__(self, dim, num_heads, mlp_hidden_dim, qkv_bias=False, qk_scale=None, drop=0., attn_drop=0.,
                 drop_path=0., act_layer=nn.GELU, norm_layer=nn.LayerNorm):
        super().__init__()
        self.norm1 = norm_layer(dim)
        self.attn = Attention(
            dim, num_heads=num_heads, qkv_bias=qkv_bias, qk_scale=qk_scale, attn_drop=attn_drop, proj_drop=drop)
        self.drop_path = DropPath(drop_path) if drop_path > 0. else nn.Identity()
        self.norm2 = norm_layer(dim)
        self.mlp = Mlp(in_features=dim, hidden_features=mlp_hidden_dim, act_layer=act_layer, drop=drop)

    def forward(self, x):
        x = x + self.drop_path(self.attn(self.norm1(x)))
        x = x + self.drop_path(self.mlp(self.norm2(x)))
        return x


class Model(nn.Module):
    def __init__(self, num_frame=9, num_joints=17, in_chans=2, embed_dim_ratio=32, depth=4,
                 num_heads=8, mlp_ratio=2., qkv_bias=True, qk_scale=None,
                 drop_rate=0., attn_drop_rate=0., drop_path_rate=0.2, norm_layer=None):
        """    ##########hybrid_backbone=None, representation_size=None,
        Args:
            num_frame (int, tuple): input frame number
            num_joints (int, tuple): joints number
            in_chans (int): number of input channels, 2D joints have 2 channels: (x,y)
            embed_dim_ratio (int): embedding dimension ratio
            depth (int): depth of transformer
            num_heads (int): number of attention heads
            mlp_ratio (int): ratio of mlp hidden dim to embedding dim
            qkv_bias (bool): enable bias for qkv if True
            qk_scale (float): override default qk scale of head_dim ** -0.5 if set
            drop_rate (float): dropout rate
            attn_drop_rate (float): attention dropout rate
            drop_path_rate (float): stochastic depth rate
            norm_layer: (nn.Module): normalization layer
        """
        super().__init__()

        view_num = 4
        embed_dim = embed_dim_ratio * num_joints
        embed_dim2 = embed_dim_ratio * num_frame
        embed_dim3 = view_num * embed_dim
        out_dim = num_joints * 3

        self.channel_embedding = nn.Linear(2*num_frame, embed_dim2)
        self.View_pos_embed = nn.Parameter(torch.zeros(1, view_num, embed_dim))
        self.Spatial_pos_embed = nn.Parameter(torch.zeros(1, num_joints, embed_dim2))
        self.Temporal_pos_embed = nn.Parameter(torch.zeros(1, num_frame, embed_dim))

        self.pos_drop = nn.Dropout(p=0.)
        self.conv = nn.Sequential(
            nn.BatchNorm2d(4, momentum=0.1),
            nn.Conv2d(4, 1, kernel_size=opt.mvf_kernel, stride=1, padding=int(opt.mvf_kernel // 2), bias=False),
            nn.ReLU(inplace=True),
        )
        self.head = nn.Sequential(
            nn.LayerNorm(embed_dim3),
            nn.Linear(embed_dim3, out_dim),
        )

        norm_layer = partial(nn.LayerNorm, eps=1e-6)
        self.View_norm = norm_layer(embed_dim)
        self.Spatial_norm = norm_layer(embed_dim2)
        self.Temporal_norm = norm_layer(embed_dim)

        self.block_depth = depth
        mlp_hidden_dim = 1024
        dpr = [x.item() for x in torch.linspace(0, drop_path_rate, depth)]

        self.VTblocks = nn.ModuleList([
            Block(
                dim=embed_dim, num_heads=num_heads, mlp_hidden_dim=mlp_hidden_dim, qkv_bias=qkv_bias, qk_scale=qk_scale,
                drop=drop_rate, attn_drop=attn_drop_rate, drop_path=dpr[i], norm_layer=norm_layer)
            for i in range(depth)])

        self.STblocks = nn.ModuleList([
            Block(
                dim=embed_dim2, num_heads=num_heads, mlp_hidden_dim=mlp_hidden_dim, qkv_bias=qkv_bias, qk_scale=qk_scale,
                drop=drop_rate, attn_drop=attn_drop_rate, drop_path=dpr[i], norm_layer=norm_layer)
            for i in range(depth)])

        self.TTblocks = nn.ModuleList([
            Block(
                dim=embed_dim, num_heads=num_heads, mlp_hidden_dim=mlp_hidden_dim, qkv_bias=qkv_bias, qk_scale=qk_scale,
                drop=drop_rate, attn_drop=attn_drop_rate, drop_path=dpr[i], norm_layer=norm_layer)
            for i in range(depth)])

    def forward(self, x):
        b, f, v, j, c = x.shape
        x = rearrange(x, 'b f v j c -> (b v) j (c f)')
        x1 = self.channel_embedding(x)
        x = x1 + self.Spatial_pos_embed
        x = self.pos_drop(x)
        x = self.STblocks[0](x)
        x = self.Spatial_norm(x)
        x = x + x1

        x1 = rearrange(x, '(b v) j (c f) -> (b f) v (c j)', b=b, j=j, f=f, v=v)
        x = x1+self.View_pos_embed
        x = self.pos_drop(x)
        x = self.VTblocks[0](x)
        x = self.View_norm(x)
        x = x + x1

        x1 = rearrange(x, '(b f) v (c j) -> (b v) f (c j)', b=b, j=j, f=f)
        x = x1+self.Temporal_pos_embed
        x = self.pos_drop(x)
        x = self.TTblocks[0](x)
        x = self.Temporal_norm(x)
        x = x + x1

        ## SVT forward
        x = rearrange(x, '(b v) f (c j) -> b f v j c', b=b, j=j, v=v)
        for i in range(1, self.block_depth):
            x = rearrange(x, 'b f v j c -> (b v) j (c f)')
            stblocks = self.STblocks[i]
            vtblocks = self.VTblocks[i]
            ttblocks = self.TTblocks[i]

            x1 = stblocks(x)
            x = x + x1
            x = self.Spatial_norm(x)
            x = rearrange(x, '(b v) j (c f) -> (b f) v (c j)', b=b, j=j, f=f)

            x1 = vtblocks(x)
            x = x + x1
            x = self.View_norm(x)
            x = rearrange(x, '(b f) v (c j) -> (b v) f (c j)', b=b, j=j, f=f)

            x1 = ttblocks(x)
            x = x + x1
            x = self.Temporal_norm(x)
            x = rearrange(x, '(b v) f (c j) -> b f v j c', b=b, j=j, v=v)

        x = rearrange(x, 'b f v j c -> b f (v j c)', b=b, j=j, v=v)
        x = self.head(x)

        x = x.view(b, opt.frames, j, -1)

        return x
