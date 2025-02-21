import torch
from torch.utils import checkpoint

# from SourceCodeTools.models.graph.basis_gatconv import BasisGATConv
from SourceCodeTools.models.graph.rgcn_sampling import RGCNSampling, RelGraphConvLayer, CkptGATConv

import torch as th
import torch.nn as nn
import torch.nn.functional as F
import dgl
import dgl.nn as dglnn
# import tqdm
from SourceCodeTools.models.Embedder import Embedder

from SourceCodeTools.nlp import token_hasher

class AttentiveAggregator(nn.Module):
    def __init__(self, emb_dim, num_dst_embeddings=3000, dropout=0., use_checkpoint=False):
        super(AttentiveAggregator, self).__init__()
        self.att = nn.MultiheadAttention(emb_dim, num_heads=1, dropout=dropout)
        self.query_emb = nn.Embedding(num_dst_embeddings, emb_dim)
        self.num_query_buckets = num_dst_embeddings
        self.use_checkpoint = use_checkpoint

        # self.query_emb = nn.ParameterList([nn.Parameter(th.Tensor(1, emb_dim, )) for i in range(num_dst_embeddings)])

        self.dummy_tensor = th.ones(1, dtype=th.float32, requires_grad=True)

    def do_stuff(self, query, key, value, dummy=None):
        att_out, att_w = self.att(query, key, value)
        return att_out, att_w

    # def custom(self):
    #     def custom_forward(*inputs):
    #         query, key, value = inputs
    #         return self.do_stuff(query, key, value)
    #     return custom_forward

    def forward(self, list_inputs, dsttype):  # pylint: disable=unused-argument
        if len(list_inputs) == 1:
            return list_inputs[0]
        key = value = th.stack(list_inputs)#.squeeze(dim=1)
        query = self.query_emb(th.LongTensor([token_hasher(dsttype, self.num_query_buckets)]).to(self.att.in_proj_bias.device)).unsqueeze(0).repeat(1, key.shape[1], 1)
        # query = self.query_emb[token_hasher(dsttype, self.num_query_buckets)].unsqueeze(0).repeat(1, key.shape[1], 1)
        if self.use_checkpoint:
            att_out, att_w = checkpoint.checkpoint(self.do_stuff, query, key, value, self.dummy_tensor)
        else:
            att_out, att_w = self.do_stuff(query, key, value)
        # att_out, att_w = self.att(query, key, value)
        # return att_out.mean(0)#.unsqueeze(1)
        return att_out.mean(0).unsqueeze(1)


from torch.nn import init
class NZBiasGraphConv(dglnn.GraphConv):
    def __init__(self, *args, **kwargs):
        super(NZBiasGraphConv, self).__init__(*args, **kwargs)
        self.use_checkpoint = True
        self.dummy_tensor = th.ones(1, dtype=th.float32, requires_grad=True)

    def reset_parameters(self):
        if self.weight is not None:
            init.xavier_uniform_(self.weight)
        if self.bias is not None:
            init.normal_(self.bias)

    def custom(self, graph):
        def custom_forward(*inputs):
            feat0, feat1, weight, _ = inputs
            return super(NZBiasGraphConv, self).forward(graph, (feat0, feat1), weight=weight)
        return custom_forward

    def forward(self, graph, feat, weight=None):
        if self.use_checkpoint:
            return checkpoint.checkpoint(self.custom(graph), feat[0], feat[1], weight, self.dummy_tensor) #.squeeze(1)
        else:
            return super(NZBiasGraphConv, self).forward(graph, feat, weight=weight) #.squeeze(1)


class RGANLayer(RelGraphConvLayer):
    def __init__(self,
                 in_feat,
                 out_feat,
                 rel_names,
                 ntype_names,
                 num_bases,
                 *,
                 weight=True,
                 bias=True,
                 activation=None,
                 self_loop=False,
                 dropout=0.0, use_gcn_checkpoint=False, use_att_checkpoint=False):
        self.use_att_checkpoint = use_att_checkpoint
        super(RGANLayer, self).__init__(
            in_feat, out_feat, rel_names, ntype_names, num_bases,
            weight=weight, bias=bias, activation=activation, self_loop=self_loop, dropout=dropout,
            use_gcn_checkpoint=use_gcn_checkpoint
        )

    def create_conv(self, in_feat, out_feat, rel_names):
        # self.attentive_aggregator = AttentiveAggregator(out_feat, use_checkpoint=self.use_att_checkpoint)
        #
        # num_heads = 1
        # basis_size = 10
        # basis = torch.nn.Parameter(torch.Tensor(2, basis_size, in_feat, out_feat * num_heads))
        # attn_basis = torch.nn.Parameter(torch.Tensor(2, basis_size, num_heads, out_feat))
        # basis_coef = nn.ParameterDict({rel: torch.nn.Parameter(torch.rand(basis_size,)) for rel in rel_names})
        #
        # torch.nn.init.xavier_normal_(basis, gain=1.)
        # torch.nn.init.xavier_normal_(attn_basis, gain=1.)

        self.conv = dglnn.HeteroGraphConv({
            rel: NZBiasGraphConv(
                in_feat, out_feat, norm='right', weight=False, bias=True, allow_zero_in_degree=True,# activation=self.activation
            )
            # rel: BasisGATConv(
            #     (in_feat, in_feat), out_feat, num_heads=num_heads,
            #     basis=basis,
            #     attn_basis=attn_basis,
            #     basis_coef=basis_coef[rel],
            #     use_checkpoint=self.use_gcn_checkpoint
            # )
            for rel in rel_names
        }, aggregate="mean") #self.attentive_aggregator)
        # self.conv = dglnn.HeteroGraphConv({
        #     rel: CkptGATConv((in_feat, in_feat), out_feat, num_heads=num_heads, use_checkpoint=self.use_gcn_checkpoint)
        #     for rel in rel_names
        # }, aggregate="mean") #self.attentive_aggregator)


class RGAN(RGCNSampling):
    def __init__(self,
                 g,
                 h_dim, num_classes,
                 num_bases,
                 num_hidden_layers=1,
                 dropout=0,
                 use_self_loop=False,
                 activation=F.relu, use_gcn_checkpoint=False, use_att_checkpoint=False, **kwargs):
        super(RGCNSampling, self).__init__()
        self.g = g
        self.h_dim = h_dim
        self.out_dim = num_classes
        self.activation = activation

        self.rel_names = list(set(g.etypes))
        self.rel_names.sort()
        self.ntype_names = list(set(g.ntypes))
        self.ntype_names.sort()
        if num_bases < 0 or num_bases > len(self.rel_names):
            self.num_bases = len(self.rel_names)
        else:
            self.num_bases = num_bases
        self.num_hidden_layers = num_hidden_layers
        self.dropout = dropout
        self.use_self_loop = use_self_loop

        self.layers = nn.ModuleList()
        # i2h
        self.layers.append(RGANLayer(
            self.h_dim, self.h_dim, self.rel_names, self.ntype_names,
            self.num_bases, activation=self.activation, self_loop=self.use_self_loop,
            dropout=self.dropout, weight=False, use_gcn_checkpoint=use_gcn_checkpoint,
            use_att_checkpoint=use_att_checkpoint))
        # h2h
        for i in range(self.num_hidden_layers):
            self.layers.append(RGANLayer(
                self.h_dim, self.h_dim, self.rel_names, self.ntype_names,
                self.num_bases, activation=self.activation, self_loop=self.use_self_loop,
                dropout=self.dropout, weight=False, use_gcn_checkpoint=use_gcn_checkpoint,
            use_att_checkpoint=use_att_checkpoint))  # changed weight for GATConv
            # TODO
            # think of possibility switching to GAT
            # weight=False
        # h2o
        self.layers.append(RGANLayer(
            self.h_dim, self.out_dim, self.rel_names, self.ntype_names,
            self.num_bases, activation=None,
            self_loop=self.use_self_loop, weight=False, use_gcn_checkpoint=use_gcn_checkpoint,
            use_att_checkpoint=use_att_checkpoint))  # changed weight for GATConv
        # TODO
        # think of possibility switching to GAT
        # weight=False

        self.emb_size = num_classes
        self.num_layers = len(self.layers)


class OneStepGRU(nn.Module):
    def __init__(self, dim, use_checkpoint=False):
        super(OneStepGRU, self).__init__()
        self.gru_rx = nn.Linear(dim, dim)
        self.gru_rh = nn.Linear(dim, dim)
        self.gru_zx = nn.Linear(dim, dim)
        self.gru_zh = nn.Linear(dim, dim)
        self.gru_nx = nn.Linear(dim, dim)
        self.gru_nh = nn.Linear(dim, dim)
        self.act_r = nn.Sigmoid()
        self.act_z = nn.Sigmoid()
        self.act_n = nn.Tanh()
        self.use_checkpoint = use_checkpoint
        self.dummy_tensor = th.ones(1, dtype=th.float32, requires_grad=True)

    def do_stuff(self, x, h, dummy_tensor=None):
        # x = x.unsqueeze(1)
        r = self.act_r(self.gru_rx(x) + self.gru_rh(h))
        z = self.act_z(self.gru_zx(x) + self.gru_zh(h))
        n = self.act_n(self.gru_nx(x) + self.gru_nh(r * h))
        return (1 - z) * n + z * h

    def forward(self, x, h):
        if self.use_checkpoint:
            h = checkpoint.checkpoint(self.do_stuff, x, h, self.dummy_tensor)
        else:
            h = self.do_stuff(x, h)
        return h


class RGGANLayer(RGANLayer):
    def __init__(self,
                 in_feat,
                 out_feat,
                 rel_names,
                 ntype_names,
                 num_bases,
                 *,
                 weight=True,
                 bias=True,
                 activation=None,
                 self_loop=False,
                 dropout=0.0, use_gcn_checkpoint=False, use_att_checkpoint=False, use_gru_checkpoint=False):
        super(RGGANLayer, self).__init__(
            in_feat, out_feat, rel_names, ntype_names, num_bases, weight=weight, bias=bias, activation=activation,
            self_loop=self_loop, dropout=dropout, use_gcn_checkpoint=use_gcn_checkpoint,
            use_att_checkpoint=use_att_checkpoint
        )
        # self.mix_weights = nn.Parameter(torch.randn(3).reshape((3,1,1)))

        # self.gru = OneStepGRU(out_feat, use_checkpoint=use_gru_checkpoint)

    def forward(self, g, inputs, h0):
        """Forward computation

        Parameters
        ----------
        g : DGLHeteroGraph
            Input graph.
        inputs : dict[str, torch.Tensor]
            Node feature for each node type.

        Returns
        -------
        dict[str, torch.Tensor]
            New node features for each node type.
        """
        g = g.local_var()
        if self.use_weight:
            weight = self.basis() if self.use_basis else self.weight
            wdict = {self.rel_names[i] : {'weight' : w.squeeze(0)}
                     for i, w in enumerate(th.split(weight, 1, dim=0))}
            # if self.self_loop:
            #     self_loop_weight = self.loop_weight_basis() if self.use_basis else self.loop_weight
            #     self_loop_wdict = {self.ntype_names[i]: w.squeeze(0)
            #              for i, w in enumerate(th.split(self_loop_weight, 1, dim=0))}
        else:
            wdict = {}

        if g.is_block:
            inputs_src = inputs
            # the begginning of src and dst indexes match, that is why we can simply slice the first
            # nodes to get dst embeddings
            inputs_dst = {k: v[:g.number_of_dst_nodes(k)] for k, v in inputs.items()}
        else:
            inputs_src = inputs_dst = inputs

        hs = self.conv(g, inputs_src, mod_kwargs=wdict)

        def _apply(ntype, h):
            if self.self_loop:
                # h = h + th.matmul(inputs_dst[ntype], self_loop_wdict[ntype])
                h = h + th.matmul(inputs_dst[ntype], self.loop_weight)
                # mix = nn.functional.softmax(self.mix_weights, dim=0)
                # h = h - inputs_dst[ntype] + th.matmul(inputs_dst[ntype], self.loop_weight)  #+ h0[ntype][:h.size(0), :]
                # h = h + th.matmul(inputs_dst[ntype], self.loop_weight) + h0[ntype][:h.size(0), :]
                # h = (torch.stack([h, th.matmul(inputs_dst[ntype], self.loop_weight), h0[ntype][:h.size(0), :]], dim=0) * mix).sum(0)
            if self.bias:
                h = h + self.bias_dict[ntype]
                # h = h + self.h_bias
            if self.activation:
                h = self.activation(h)
            return self.dropout(h)

        # the code above is identical to RelGraphConvLayer

        # TODO
        # think of possibility switching to GAT
        return {ntype: _apply(ntype, h) for ntype, h in hs.items()}
        # h_gru_input = {ntype : _apply(ntype, h) for ntype, h in hs.items()}
        #
        # return {dsttype: self.gru(h_dst, inputs_dst[dsttype].unsqueeze(1)).squeeze(dim=1) for dsttype, h_dst in h_gru_input.items()}

class RGGAN(RGAN):
    """A gated recurrent unit (GRU) cell

    .. math::

        \begin{array}{ll}
        r = \sigma(W_{ir} x + b_{ir} + W_{hr} h + b_{hr}) \\
        z = \sigma(W_{iz} x + b_{iz} + W_{hz} h + b_{hz}) \\
        n = \tanh(W_{in} x + b_{in} + r * (W_{hn} h + b_{hn})) \\
        h' = (1 - z) * n + z * h
        \end{array}

    where :math:`\sigma` is the sigmoid function, and :math:`*` is the Hadamard product."""
    def __init__(self,
                 g,
                 h_dim, node_emb_size,
                 num_bases,
                 n_layers=1,
                 dropout=0,
                 use_self_loop=False,
                 activation=F.relu,
                 use_gcn_checkpoint=False, use_att_checkpoint=False, use_gru_checkpoint=False):
        super(RGCNSampling, self).__init__()
        self.g = g
        self.h_dim = h_dim
        self.out_dim = node_emb_size
        self.activation = activation

        assert h_dim == node_emb_size, f"Parameter h_dim and num_classes should be equal in {self.__class__.__name__}"

        self.rel_names = list(set(g.etypes))
        self.ntype_names = list(set(g.ntypes))
        self.rel_names.sort()
        self.ntype_names.sort()
        if num_bases < 0 or num_bases > len(self.rel_names):
            self.num_bases = len(self.rel_names)
        else:
            self.num_bases = num_bases

        self.dropout = dropout
        self.use_self_loop = use_self_loop

        # i2h
        self.layer = RGGANLayer(
            self.h_dim, self.h_dim, self.rel_names, self.ntype_names,
            self.num_bases, activation=self.activation, self_loop=self.use_self_loop,
            dropout=self.dropout, weight=True, use_gcn_checkpoint=use_gcn_checkpoint, # : )
            use_att_checkpoint=use_att_checkpoint, use_gru_checkpoint=use_gru_checkpoint
        )
        # TODO
        # think of possibility switching to GAT
        # weight=False

        self.emb_size = node_emb_size
        self.num_layers = n_layers
        self.layers = [self.layer] * n_layers
        self.layer_norm = nn.ModuleList([nn.LayerNorm([self.h_dim]) for _ in range(self.num_layers)])
