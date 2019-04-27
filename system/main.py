import torch
from torch import nn
import argparse
import yaml
import models
from data.dataset import TextDataset, word_to_idx, max_len, embeds, restore_input
from torch.utils.data import DataLoader
from torch import optim
from tensorboardX import SummaryWriter
from utils import AverageMeter


parser = argparse.ArgumentParser()
parser.add_argument('--config', type=str, required=True)
args = parser.parse_args()

if torch.cuda.is_available():
    use_gpu = True
else:
    use_gpu = False

def main ():
    with open(args.config) as f:
        config = yaml.load(f)
        for k, v in config.items():
            setattr(args, k, v)

    model = models.__dict__[args.model](ch_size=args.ch_size, embed_dim=args.embed_dim, vocab_size=len(embeds), max_len=max_len)
    model.init_embeds(embeds)
    if use_gpu:
        model = model.cuda()
        if args.dataparallel:
            model = nn.DataParallel(model)

    train_data = TextDataset("data/train")
    train_loader = DataLoader(train_data, batch_size=args.batch_size, shuffle=True, num_workers=args.num_workers)
    val_data = TextDataset("data/val")
    val_loader = DataLoader(val_data, batch_size=args.batch_size, shuffle=True, num_workers=args.num_workers)

    criterion = nn.CrossEntropyLoss()
    if use_gpu:
        criterion = criterion.cuda()

    optimizer = optim.SGD(model.parameters(), lr=args.base_lr,
                          momentum=args.momentum, weight_decay=args.weight_decay)
    scheduler = optim.lr_scheduler.MultiStepLR(optimizer, args.steps)

    writer = SummaryWriter(args.save_path)

    for i in range(args.epoch):
        scheduler.step()
        train(model, train_loader, criterion, optimizer, writer, i)
        validate(model, val_loader, criterion, writer, i)

def train(model, loader, criterion, optimizer, writer, epoch):
    model.train()
    for i, (input, label) in enumerate(loader):
        # print(input, label)

        if use_gpu:
            input = input.cuda()
            label = label.cuda()

        output = model(input)
        loss = criterion(output, label)

        optimizer.zero_grad()
        loss.backward()
        optimizer.step()

        loss.detach_()
        output.detach_()
        v_eq = (torch.max(output, 1)[1] == label).double()
        acc = torch.mean(v_eq)

        if i % args.print_freq == 0:
            print("Training [{}/{}]\tLoss:{:.3f}\tAcc:{:.3f}".format(i, len(loader),
                                                                     loss.item(), acc.item()))
            writer.add_scalar("Train/Loss", loss.item(), epoch*len(loader)+i)
            writer.add_scalar("Train/Acc", acc.item(), epoch*len(loader)+i)

def validate(model, loader, criterion, writer, epoch):
    model.eval()
    loss_meter = AverageMeter()
    acc_meter = AverageMeter()
    wrong_posi = []
    wrong_nega = []
    with torch.no_grad():
        for i, (input, label) in enumerate(loader):

            input = input.cuda()
            label = label.cuda()

            output = model(input)
            loss = criterion(output, label)

            v_eq = (torch.max(output, 1)[1] == label).double()
            acc = torch.mean(v_eq)

            acc_meter.update(acc.item(), input.shape[0])
            loss_meter.update(loss.item(), input.shape[0])
            print("Validating [{}/{}]".format(i, len(loader)))

    print("Val results [{}]: {:.3f}".format(epoch, acc_meter.avg))
    writer.add_scalar("Val/loss", loss_meter.avg, epoch)
    writer.add_scalar("Val/acc", acc_meter.avg, epoch)
    if acc_meter.avg > 0.75:
        with torch.no_grad():
            for i, (input, label) in enumerate(loader):

                input = input.cuda()

                output = model(input)

                pred = torch.max(output, 1)[1].cpu()
                v_eq = (pred == label)

                v_eq = v_eq.numpy()
                input = input.cpu().numpy()
                for i in range(len(v_eq)):
                    if v_eq[i] == 0:
                        print(">>>>>>>>>")
                        print(restore_input(input[i]), label[i], pred[i])
                        print("<<<<<<<<<")
        exit()


if __name__ == "__main__":
    main ()
