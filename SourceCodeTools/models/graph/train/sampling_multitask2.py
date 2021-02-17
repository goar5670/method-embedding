import os
import sys
from copy import copy
from typing import Tuple

import torch
import torch.nn as nn
from torch.utils.tensorboard import SummaryWriter
from torch.optim.lr_scheduler import ExponentialLR
import dgl
from math import ceil
from time import time
from os.path import join
import logging

from SourceCodeTools.models.Embedder import Embedder
from SourceCodeTools.models.graph.ElementEmbedder import ElementEmbedderWithBpeSubwords
from SourceCodeTools.models.graph.ElementEmbedderBase import ElementEmbedderBase
from SourceCodeTools.models.graph.train.objectives import Objective
from SourceCodeTools.models.graph.train.utils import BestScoreTracker  # create_elem_embedder
from SourceCodeTools.models.graph.LinkPredictor import LinkPredictor
from SourceCodeTools.models.graph.NodeEmbedder import NodeEmbedder


def _compute_accuracy(pred_, true_):
    return torch.sum(pred_ == true_).item() / len(true_)


class SamplingMultitaskTrainer:

    def __init__(self,
                 dataset=None, model_name=None, model_params=None,
                 trainer_params=None, restore=None, device=None,
                 pretrained_embeddings_path=None,
                 tokenizer_path=None
                 ):

        self.graph_model = model_name(dataset.g, **model_params).to(device)
        self.model_params = model_params
        self.trainer_params = trainer_params
        self.device = device
        self.epoch = 0
        self.batch = 0
        self.dtype = torch.float32
        self.create_node_embedder(
            dataset, tokenizer_path, n_dims=model_params["h_dim"],
            pretrained_path=pretrained_embeddings_path, n_buckets=trainer_params["embedding_table_size"]
        )

        self.summary_writer = SummaryWriter(self.model_base_path)

        self.create_objectives(dataset, tokenizer_path)

        if restore:
            self.restore_from_checkpoint(self.model_base_path)

        self.optimizer = self._create_optimizer()

        self.lr_scheduler = ExponentialLR(self.optimizer, gamma=1.0)

    def create_objectives(self, dataset, tokenizer_path):
        self.objectives = nn.ModuleList()
        self.create_node_name_objective(dataset, tokenizer_path)
        self.create_var_use_objective(dataset, tokenizer_path)
        self.create_api_call_objective(dataset, tokenizer_path)

    def create_node_name_objective(self, dataset, tokenizer_path):
        self.objectives.append(
            Objective(
                "node_name", "subword_ranker", self.graph_model, self.node_embedder, dataset.nodes,
                dataset.load_node_names, self.device,
                self.sampling_neighbourhood_size, self.batch_size,
                tokenizer_path=tokenizer_path, target_emb_size=self.elem_emb_size, link_predictor_type="nn"
            )
        )

    def create_var_use_objective(self, dataset, tokenizer_path):
        self.objectives.append(
            Objective(
                "var_use", "subword_ranker", self.graph_model, self.node_embedder, dataset.nodes,
                dataset.load_var_use, self.device,
                self.sampling_neighbourhood_size, self.batch_size,
                tokenizer_path=tokenizer_path, target_emb_size=self.elem_emb_size, link_predictor_type="nn"
            )
        )

    def create_api_call_objective(self, dataset, tokenizer_path):
        self.objectives.append(
            Objective(
                "api_call", "graph_link_prediction", self.graph_model, self.node_embedder, dataset.nodes,
                dataset.load_api_call, self.device,
                self.sampling_neighbourhood_size, self.batch_size,
                tokenizer_path=tokenizer_path, target_emb_size=self.elem_emb_size, link_predictor_type="nn"
            )
        )

    def create_node_embedder(self, dataset, tokenizer_path, n_dims=None, pretrained_path=None, n_buckets=500000):
        from SourceCodeTools.nlp.embed.fasttext import load_w2v_map

        if pretrained_path is not None:
            pretrained = load_w2v_map(pretrained_path)
        else:
            pretrained = None

        if pretrained_path is None and n_dims is None:
            raise ValueError(f"Specify embedding dimensionality or provide pretrained embeddings")
        elif pretrained_path is not None and n_dims is not None:
            assert n_dims == pretrained.n_dims, f"Requested embedding size and pretrained embedding " \
                                                f"size should match: {n_dims} != {pretrained.n_dims}"
        elif pretrained_path is not None and n_dims is None:
            n_dims = pretrained.n_dims

        if pretrained is not None:
            logging.info(f"Loading pretrained embeddings...")
        logging.info(f"Input embedding size is {n_dims}")

        self.node_embedder = NodeEmbedder(
            nodes=dataset.nodes,
            emb_size=n_dims,
            # tokenizer_path=tokenizer_path,
            dtype=self.dtype,
            pretrained=dataset.buckets_from_pretrained_embeddings(pretrained_path, n_buckets)
            if pretrained_path is not None else None,
            n_buckets=n_buckets
        )

    @property
    def lr(self):
        return self.trainer_params['lr']

    @property
    def batch_size(self):
        return self.trainer_params['batch_size']

    @property
    def sampling_neighbourhood_size(self):
        return self.trainer_params['sampling_neighbourhood_size']

    @property
    def neg_sampling_factor(self):
        return self.trainer_params['neg_sampling_factor']

    @property
    def epochs(self):
        return self.trainer_params['epochs']

    @property
    def elem_emb_size(self):
        return self.trainer_params['elem_emb_size']

    @property
    def node_name_file(self):
        return self.trainer_params['node_name_file']

    @property
    def var_use_file(self):
        return self.trainer_params['var_use_file']

    @property
    def call_seq_file(self):
        return self.trainer_params['call_seq_file']

    @property
    def model_base_path(self):
        return self.trainer_params['model_base_path']

    @property
    def pretraining(self):
        return self.epoch >= self.trainer_params['pretraining_phase']

    @property
    def do_save(self):
        return self.trainer_params['save_checkpoints']

    def write_summary(self, scores, batch_step):
        # main_name = os.path.basename(self.model_base_path)
        for var, val in scores.items():
            # self.summary_writer.add_scalar(f"{main_name}/{var}", val, batch_step)
            self.summary_writer.add_scalar(var, val, batch_step)
        # self.summary_writer.add_scalars(main_name, scores, batch_step)

    def write_hyperparams(self, scores, epoch):
        params = copy(self.model_params)
        params["epoch"] = epoch
        main_name = os.path.basename(self.model_base_path)
        params = {k: v for k, v in params.items() if type(v) in {int, float, str, bool, torch.Tensor}}

        main_name = os.path.basename(self.model_base_path)
        scores = {f"h_metric/{k}": v for k, v in scores.items()}
        self.summary_writer.add_hparams(params, scores, run_name=f"h_metric/{epoch}")

    def _evaluate_objectives(
            self, loader_node_name, loader_var_use,
            loader_api_call, neg_sampling_factor
    ):

        node_name_loss, node_name_acc = self._evaluate_embedder(
            self.ee_node_name, self.lp_node_name, loader_node_name, neg_sampling_factor=neg_sampling_factor
        )

        var_use_loss, var_use_acc = self._evaluate_embedder(
            self.ee_var_use, self.lp_var_use, loader_var_use, neg_sampling_factor=neg_sampling_factor
        )

        api_call_loss, api_call_acc = self._evaluate_nodes(self.ee_api_call, self.lp_api_call,
                                                           self._create_api_call_loader, loader_api_call,
                                                           neg_sampling_factor=neg_sampling_factor)

        loss = node_name_loss + var_use_loss + api_call_loss

        return loss, node_name_acc, var_use_acc, api_call_acc

    def _create_optimizer(self):
        parameters = nn.ParameterList(self.graph_model.parameters())
        parameters.extend(self.node_embedder.parameters())
        [parameters.extend(objective.parameters()) for objective in self.objectives]

        optimizer = torch.optim.Adam(
            [{"params": parameters}], lr=self.lr
        )
        return optimizer

    def train_all(self):
        """
        Training procedure for the model with node classifier
        :return:
        """

        summary_dict = {}

        for epoch in range(self.epoch, self.epochs):
            self.epoch = epoch

            start = time()

            keep_training = True

            summary_dict = {}
            while keep_training:

                loss_accum = 0

                summary = {}

                try:
                    loaders = [objective.loader_next("train") for objective in self.objectives]
                except StopIteration:
                    break

                self.optimizer.zero_grad()
                for objective, (input_nodes, seeds, blocks) in zip(self.objectives, loaders):

                    loss, acc = objective(input_nodes, seeds, blocks, train_embeddings=self.pretraining)

                    loss = loss / len(self.objectives)  # assumes the same batch size for all objectives
                    loss_accum += loss.item()
                    loss.backward()

                    summary.update({
                        f"Loss/train/{objective.name}_vs_batch": loss.item(),
                        f"Accuracy/train/{objective.name}_vs_batch": acc,
                    })

                self.optimizer.step()

                self.write_summary(summary, self.batch)
                summary_dict.update(summary)

                self.batch += 1
                summary = {
                    f"Loss/train": loss_accum,
                }
                self.write_summary(summary, self.batch)
                summary_dict.update(summary)

            for objective in self.objectives:
                objective.reset_iterator("train")

            for objective in self.objectives:
                objective.eval()

                with torch.set_grad_enabled(False):

                    val_loss, val_acc = objective.evaluate("val")
                    test_loss, test_acc = objective.evaluate("test")

                summary = {
                        f"Accuracy/test/{objective.name}_vs_batch": test_acc,
                        f"Accuracy/val/{objective.name}_vs_batch": val_acc,
                    }

                self.write_summary(summary, self.batch)
                summary_dict.update(summary)

                objective.train()

            self.write_hyperparams({k.replace("vs_batch", "vs_epoch"): v for k,v in summary_dict.items()}, self.epoch)

            end = time()

            print(f"Epoch: {self.epoch}, Time: {int(end - start)} s", end="\t")
            print(summary_dict)

            if self.do_save:
                self.save_checkpoint(self.model_base_path)

            self.lr_scheduler.step()

    def save_checkpoint(self, checkpoint_path=None, checkpoint_name=None, **kwargs):

        checkpoint_path = join(checkpoint_path, "saved_state.pt")

        param_dict = {
            'graph_model': self.graph_model.state_dict(),
            'node_embedder': self.node_embedder.state_dict(),
            "epoch": self.epoch,
            "batch": self.batch
        }

        for objective in self.objectives:
            param_dict[objective.name] = objective.custom_state_dict()

        if len(kwargs) > 0:
            param_dict.update(kwargs)

        torch.save(param_dict, checkpoint_path)

    def restore_from_checkpoint(self, checkpoint_path):
        checkpoint = torch.load(join(checkpoint_path, "saved_state.pt"))
        self.graph_model.load_state_dict(checkpoint['graph_model'])
        self.node_embedder.load_state_dict(checkpoint['graph_model'])
        for objective in self.objectives():
            objective.custom_load_state_dict(checkpoint[objective.name])
        self.epoch = checkpoint['epoch']
        self.batch = checkpoint['batch']
        logging.info(f"Restored from epoch {checkpoint['epoch']}")

    def final_evaluation(self):

        summary_dict = {}

        for objective in self.objectives:
            objective.reset_iterator("train")
            objective.reset_iterator("val")
            objective.reset_iterator("test")

        with torch.set_grad_enabled(False):

            for objective in self.objectives:

                train_loss, train_acc = objective.evaluate("train")
                val_loss, val_acc = objective.evaluate("val")
                test_loss, test_acc = objective.evaluate("test")

                summary = {
                    f"Accuracy/train/{objective.name}_final": train_acc,
                    f"Accuracy/test/{objective.name}_final": test_acc,
                    f"Accuracy/val/{objective.name}_final": val_acc,
                }

                summary_dict.update(summary)

        self.write_hyperparams(summary_dict, self.epoch)

        scores_str = ", ".join([f"{k}: {v}" for k, v in summary_dict.items()])

        print(f"Final eval: {scores_str}")

        return summary_dict

    def eval(self):
        self.graph_model.eval()
        self.node_embedder.eval()
        for objective in self.objectives:
            objective.eval()

    def train(self):
        self.graph_model.train()
        self.node_embedder.train()
        for objective in self.objectives:
            objective.train()

    def to(self, device):
        self.graph_model.to(device)
        self.node_embedder.to(device)
        for objective in self.objectives:
            objective.to(device)

    def get_embeddings(self):
        # self.graph_model.g.nodes["function"].data.keys()
        nodes = self.graph_model.g.nodes
        node_embs = {
            ntype: self.node_embedder(node_type=ntype, node_ids=nodes[ntype].data['typed_id'], train_embeddings=False)
            for ntype in self.graph_model.g.ntypes
        }

        h = self.graph_model.inference(batch_size=256, device='cpu', num_workers=0, x=node_embs)

        original_id = []
        global_id = []
        embeddings = []
        for ntype in self.graph_model.g.ntypes:
            embeddings.append(h[ntype])
            original_id.extend(nodes[ntype].data['original_id'].tolist())
            global_id.extend(nodes[ntype].data['global_graph_id'].tolist())

        embeddings = torch.cat(embeddings, dim=0).detach().numpy()

        return [Embedder(dict(zip(original_id, global_id)), embeddings)]


def select_device(args):
    device = 'cpu'
    use_cuda = args.gpu >= 0 and torch.cuda.is_available()
    if use_cuda:
        torch.cuda.set_device(args.gpu)
        device = 'cuda:%d' % args.gpu
    return device


def training_procedure(
        dataset, model_name, model_params, args, model_base_path
) -> Tuple[SamplingMultitaskTrainer, dict]:

    device = select_device(args)

    model_params['num_classes'] = args.node_emb_size
    model_params['use_gcn_checkpoint'] = args.use_gcn_checkpoint
    model_params['use_att_checkpoint'] = args.use_att_checkpoint
    model_params['use_gru_checkpoint'] = args.use_gru_checkpoint

    trainer_params = {
        'lr': model_params.pop('lr'),
        'batch_size': args.batch_size,
        'sampling_neighbourhood_size': args.num_per_neigh,
        'neg_sampling_factor': args.neg_sampling_factor,
        'epochs': args.epochs,
        # 'node_name_file': args.fname_file,
        # 'var_use_file': args.varuse_file,
        # 'call_seq_file': args.call_seq_file,
        'elem_emb_size': args.elem_emb_size,
        'model_base_path': model_base_path,
        'pretraining_phase': args.pretraining_phase,
        'use_layer_scheduling': args.use_layer_scheduling,
        'schedule_layers_every': args.schedule_layers_every,
        'embedding_table_size': args.embedding_table_size,
        'save_checkpoints': args.save_checkpoints
    }

    trainer = SamplingMultitaskTrainer(
        dataset=dataset,
        model_name=model_name,
        model_params=model_params,
        trainer_params=trainer_params,
        restore=args.restore_state,
        device=device,
        pretrained_embeddings_path=args.pretrained,
        tokenizer_path=args.tokenizer
    )

    try:
        trainer.train_all()
    except KeyboardInterrupt:
        print("Training interrupted")
    except Exception as e:
        raise e

    trainer.eval()
    scores = trainer.final_evaluation()

    trainer.to('cpu')

    return trainer, scores
