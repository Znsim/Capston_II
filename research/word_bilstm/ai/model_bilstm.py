import torch
import torch.nn as nn
from torch.nn.utils.rnn import pack_padded_sequence, pad_packed_sequence


class BiLSTMClassifier(nn.Module):
    def __init__(self, input_size: int, hidden_size: int, num_layers: int, num_classes: int,
                 bidirectional: bool = True, dropout: float = 0.5):
        super().__init__()
        self.hidden_size = hidden_size
        self.num_layers = num_layers
        self.bidirectional = bidirectional
        self.lstm = nn.LSTM(input_size=input_size, hidden_size=hidden_size,
                            num_layers=num_layers, batch_first=True,
                            bidirectional=bidirectional, dropout=dropout if num_layers>1 else 0.0)
        factor = 2 if bidirectional else 1
        self.classifier = nn.Sequential(
            nn.Dropout(dropout),
            nn.Linear(hidden_size * factor, hidden_size),
            nn.ReLU(inplace=True),
            nn.Dropout(dropout),
            nn.Linear(hidden_size, num_classes)
        )

    def forward(self, x, lengths=None):
        # x: (B, T, F)
        if lengths is not None:
            packed = pack_padded_sequence(x, lengths.cpu(), batch_first=True, enforce_sorted=False)
            out, _ = self.lstm(packed)
            out, _ = pad_packed_sequence(out, batch_first=True)
            # extract the hidden state at each sequence's actual last timestep
            idx = (lengths - 1).long().to(x.device)
            idx = idx.unsqueeze(1).unsqueeze(2).expand(-1, 1, out.size(2))
            last = out.gather(1, idx).squeeze(1)
        else:
            out, _ = self.lstm(x)
            last = out[:, -1, :]
        logits = self.classifier(last)
        return logits
