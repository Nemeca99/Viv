"""Part 6: one complete small transformer made from four attention blocks."""
from __future__ import annotations

import torch
from torch import Tensor, nn
from torch.nn import functional as F


class SelfAttentionHead(nn.Module):
    """One causal attention head with its own Q/K/V projections and weights."""

    def __init__(self, embedding_width: int, head_size: int, context_length: int):
        super().__init__()
        self.embedding_width = embedding_width
        self.head_size = head_size
        self.context_length = context_length
        self.key = nn.Linear(embedding_width, head_size, bias=False)
        self.query = nn.Linear(embedding_width, head_size, bias=False)
        self.value = nn.Linear(embedding_width, head_size, bias=False)
        self.scale = head_size ** -0.5
        self.register_buffer(
            "causal_mask",
            torch.tril(torch.ones(context_length, context_length)),
            persistent=True,
        )

    def forward(self, represented: Tensor) -> tuple[Tensor, Tensor]:
        if represented.ndim != 3 or represented.shape[-1] != self.embedding_width:
            raise ValueError("transformer_head_representation_shape_mismatch")
        _, time, _ = represented.shape
        if time <= 0 or time > self.context_length:
            raise ValueError("transformer_head_context_length_out_of_range")
        keys = self.key(represented)
        queries = self.query(represented)
        values = self.value(represented)
        scores = (queries @ keys.transpose(-2, -1)) * self.scale
        mask = self.causal_mask[:time, :time]
        scores = scores.masked_fill(mask == 0, float("-inf"))
        weights = F.softmax(scores, dim=-1)
        return weights @ values, weights


class MultiHeadAttention(nn.Module):
    """Four independent heads concatenated back to the model width."""

    def __init__(
        self,
        embedding_width: int,
        num_heads: int,
        head_size: int,
        context_length: int,
        dropout: float,
    ):
        super().__init__()
        if num_heads * head_size != embedding_width:
            raise ValueError("heads_times_head_size_must_equal_embedding_width")
        self.embedding_width = embedding_width
        self.num_heads = num_heads
        self.head_size = head_size
        self.heads = nn.ModuleList(
            SelfAttentionHead(embedding_width, head_size, context_length)
            for _ in range(num_heads)
        )
        self.projection = nn.Linear(embedding_width, embedding_width)
        self.dropout = nn.Dropout(dropout)

    def forward(self, represented: Tensor) -> tuple[Tensor, list[Tensor]]:
        head_outputs: list[Tensor] = []
        attention_weights: list[Tensor] = []
        for head in self.heads:
            output, weights = head(represented)
            head_outputs.append(output)
            attention_weights.append(weights)
        combined = torch.cat(head_outputs, dim=-1)
        return self.dropout(self.projection(combined)), attention_weights


class FeedForward(nn.Module):
    """Position-wise 128 -> 512 -> 128 GELU network with dropout."""

    def __init__(self, embedding_width: int, dropout: float):
        super().__init__()
        hidden_width = 4 * embedding_width
        self.network = nn.Sequential(
            nn.Linear(embedding_width, hidden_width),
            nn.GELU(),
            nn.Linear(hidden_width, embedding_width),
            nn.Dropout(dropout),
        )

    def forward(self, represented: Tensor) -> Tensor:
        return self.network(represented)


class TransformerBlock(nn.Module):
    """Pre-normalized attention and feed-forward residual block."""

    def __init__(
        self,
        embedding_width: int,
        num_heads: int,
        head_size: int,
        context_length: int,
        dropout: float,
    ):
        super().__init__()
        self.layer_norm_attention = nn.LayerNorm(embedding_width)
        self.self_attention = MultiHeadAttention(
            embedding_width,
            num_heads,
            head_size,
            context_length,
            dropout,
        )
        self.layer_norm_feed_forward = nn.LayerNorm(embedding_width)
        self.feed_forward = FeedForward(embedding_width, dropout)

    def forward(self, represented: Tensor) -> tuple[Tensor, list[Tensor]]:
        attention_output, weights = self.self_attention(
            self.layer_norm_attention(represented)
        )
        represented = represented + attention_output
        represented = represented + self.feed_forward(
            self.layer_norm_feed_forward(represented)
        )
        return represented, weights


class TransformerLanguageModel(nn.Module):
    """Four-block, four-head character transformer with random initialization."""

    def __init__(
        self,
        vocab_size: int,
        *,
        context_length: int = 128,
        embedding_width: int = 128,
        num_heads: int = 4,
        head_size: int = 32,
        num_layers: int = 4,
        dropout: float = 0.1,
    ):
        super().__init__()
        if not isinstance(vocab_size, int) or vocab_size <= 0:
            raise ValueError("transformer_vocab_size_must_be_positive_integer")
        if min(context_length, embedding_width, num_heads, head_size, num_layers) <= 0:
            raise ValueError("transformer_dimensions_must_be_positive")
        if not 0.0 <= dropout < 1.0:
            raise ValueError("transformer_dropout_must_be_in_zero_one_range")
        if num_heads * head_size != embedding_width:
            raise ValueError("transformer_heads_must_fill_embedding_width")
        self.vocab_size = vocab_size
        self.context_length = context_length
        self.embedding_width = embedding_width
        self.num_heads = num_heads
        self.head_size = head_size
        self.num_layers = num_layers
        self.dropout_rate = dropout
        self.token_embedding_table = nn.Embedding(vocab_size, embedding_width)
        self.position_embedding_table = nn.Embedding(context_length, embedding_width)
        self.embedding_dropout = nn.Dropout(dropout)
        self.blocks = nn.ModuleList(
            TransformerBlock(
                embedding_width,
                num_heads,
                head_size,
                context_length,
                dropout,
            )
            for _ in range(num_layers)
        )
        self.final_layer_norm = nn.LayerNorm(embedding_width)
        self.lm_head = nn.Linear(embedding_width, vocab_size)

    def _validate_ids(self, token_ids: Tensor) -> Tensor:
        if not isinstance(token_ids, Tensor) or token_ids.dtype not in (
            torch.uint8,
            torch.int8,
            torch.int16,
            torch.int32,
            torch.int64,
        ):
            raise TypeError("transformer_token_ids_must_be_integer_tensor")
        if token_ids.numel() and (
            int(token_ids.min()) < 0 or int(token_ids.max()) >= self.vocab_size
        ):
            raise ValueError("transformer_token_id_out_of_range")
        return token_ids.to(dtype=torch.long)

    def forward(
        self,
        input_ids: Tensor,
        *,
        return_attention: bool = False,
    ) -> Tensor | tuple[Tensor, list[list[Tensor]]]:
        ids = self._validate_ids(input_ids)
        if ids.ndim != 2:
            raise ValueError("transformer_input_ids_must_be_rank_two")
        _, time = ids.shape
        if time <= 0 or time > self.context_length:
            raise ValueError("transformer_context_length_out_of_range")
        token_vectors = self.token_embedding_table(ids)
        position_ids = torch.arange(time, device=ids.device)
        position_vectors = self.position_embedding_table(position_ids)
        represented = self.embedding_dropout(
            token_vectors + position_vectors.unsqueeze(0)
        )
        all_attention_weights: list[list[Tensor]] = []
        for block in self.blocks:
            represented, weights = block(represented)
            all_attention_weights.append(weights)
        logits = self.lm_head(self.final_layer_norm(represented))
        if return_attention:
            return logits, all_attention_weights
        return logits

    def loss_and_accuracy(self, logits: Tensor, target_ids: Tensor) -> tuple[Tensor, Tensor]:
        targets = self._validate_ids(target_ids)
        if logits.shape[:-1] != targets.shape or logits.shape[-1] != self.vocab_size:
            raise ValueError("transformer_logits_target_shape_mismatch")
        loss = F.cross_entropy(logits.reshape(-1, self.vocab_size), targets.reshape(-1))
        accuracy = (logits.argmax(dim=-1) == targets).to(dtype=torch.float32).mean()
        return loss, accuracy

    @torch.no_grad()
    def generate(
        self,
        context_ids: Tensor,
        *,
        max_new_tokens: int,
        temperature: float = 1.0,
        top_k: int | None = None,
        generator: torch.Generator | None = None,
    ) -> Tensor:
        if max_new_tokens < 0:
            raise ValueError("transformer_max_new_tokens_must_not_be_negative")
        if temperature < 0:
            raise ValueError("transformer_temperature_must_not_be_negative")
        if top_k is not None and (not isinstance(top_k, int) or top_k <= 0):
            raise ValueError("transformer_top_k_must_be_positive_integer")
        output = self._validate_ids(context_ids)
        if output.ndim == 1:
            output = output.unsqueeze(0)
        if output.ndim != 2 or output.shape[1] == 0:
            raise ValueError("transformer_generation_context_must_be_nonempty_rank_two")
        for _ in range(max_new_tokens):
            cropped = output[:, -self.context_length :]
            next_logits = self(cropped)[:, -1, :]
            if top_k is not None:
                effective_top_k = min(top_k, self.vocab_size)
                top_values, _ = torch.topk(next_logits, effective_top_k, dim=-1)
                cutoff = top_values[:, [-1]]
                next_logits = next_logits.masked_fill(next_logits < cutoff, float("-inf"))
            if temperature == 0:
                sampled_ids = next_logits.argmax(dim=-1, keepdim=True)
            else:
                probabilities = F.softmax(next_logits / temperature, dim=-1)
                sampled_ids = torch.multinomial(
                    probabilities,
                    num_samples=1,
                    generator=generator,
                )
            output = torch.cat((output, sampled_ids), dim=1)
        return output
