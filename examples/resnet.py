from torch import nn
from pytorch_functional import Input, FunctionalModel, layers


def classifier(flow, n_classes, pooling="avgpool"):
    if pooling == 'catpool':
        maxp = flow(nn.MaxPool2d(kernel_size=(flow.H, flow.W)))
        avgp = flow(nn.AvgPool2d(kernel_size=(flow.H, flow.W)))
        flow = maxp(layers.ConcatOpLayer(dim=1), avgp)(nn.Flatten())
    if pooling == 'avgpool':
        flow = flow(nn.AvgPool2d(kernel_size=(flow.H, flow.W)))(nn.Flatten())
    if pooling == 'maxpool':
        flow = flow(nn.MaxPool2d(kernel_size=(flow.H, flow.W)))(nn.Flatten())
    return flow(nn.Linear(flow.features, n_classes))


def ResNet(
        input_shape,
        n_classes,
        version=None,
        bootleneck=False,
        strides=(1, 2, 2),
        group_sizes=(2, 2, 2),
        channels=(16, 32, 64),
        activation=nn.ReLU(),
        final_pooling='avgpool',
        dropout=0,
        bn_ends_block=False,
        **kwargs
):
    if version:
        if version == 20:
            group_sizes = (3, 3, 3)
        elif version == 32:
            group_sizes = (5, 5, 5)
        elif version == 44:
            group_sizes = (7, 7, 7)
        elif version == 56:
            group_sizes = (9, 9, 9)
        elif version == 110:
            group_sizes = (18, 18, 18)
        elif version == 164:
            bootleneck = True
            channels = (64, 128, 256)
            group_sizes = (18, 18, 18)
        elif version == 1001:
            raise NotImplementedError(f"ResNet1001 doesn't work yet...")
            bootleneck = True
            channels = (64, 128, 256)
            group_sizes = (111, 111, 111)
        elif isinstance(version, tuple) and version[0] == "WRN":
            _, N, K = version
            assert (N - 4) % 6 == 0, "N-4 has to be divisible by 6"
            lpb = (N - 4) // 6  # layers per block
            group_sizes = (lpb, lpb, lpb)
            channels = tuple(c * K for c in channels)
        else:
            raise NotImplementedError(f"Unkown version={version}!")

    if kwargs:
        print(f"ResNet: unknown parameters: {kwargs.keys()}")

    def shortcut_func(x, channels, stride):
        if x.channels != channels or stride != 1:
            return x(nn.Conv2d(x.channels,
                               channels,
                               kernel_size=1,
                               bias=False,
                               stride=stride))
        else:
            return x

    def simple_block(flow, channels, stride):
        if preactivate_block:
            flow = flow(nn.BatchNorm2d(flow.features))(activation)

        flow = flow(nn.Conv2d(flow.channels, channels, 3, stride, 1))
        flow = flow(nn.BatchNorm2d(flow.features))(activation)

        if dropout:
            flow = flow(nn.Dropout(p=dropout))
        flow = flow(nn.Conv2d(flow.channels, channels, 3, 1, 1))

        if bn_ends_block:
            flow = flow(nn.BatchNorm2d(flow.features))(activation)
        return flow

    def bootleneck_block(flow, channels, stride):
        if preactivate_block:
            flow = flow(nn.BatchNorm2d(flow.features))(activation)

        flow = flow(nn.Conv2d(flow.channels, channels // 4, 1))
        flow = flow(nn.BatchNorm2d(flow.features))(activation)

        flow = flow(
            nn.Conv2d(flow.channels, channels // 4, 3, stride=stride, padding=1))
        flow = flow(nn.BatchNorm2d(flow.features))(activation)

        flow = flow(nn.Conv2d(flow.channels, channels, 1))
        if bn_ends_block:
            flow = flow(nn.BatchNorm2d(flow.features))(activation)
        return flow

    if bootleneck:
        block = bootleneck_block
    else:
        block = simple_block

    inputs = Input(input_shape)

    # BUILDING HEAD OF THE NETWORK
    flow = inputs(nn.Conv2d(inputs.channels, 16, 3, 1, 1))

    # BUILD THE RESIDUAL BLOCKS
    layer_idx, num_layers = 0, sum(group_sizes)
    for group_size, width, stride in zip(group_sizes, channels, strides):
        flow = flow(nn.BatchNorm2d(flow.features))(activation)
        preactivate_block = False

        for _ in range(group_size):
            layer_idx += 1
            residual = block(flow, width, stride)
            shortcut = shortcut_func(flow, width, stride)
            flow = residual + shortcut
            preactivate_block = True
            stride = 1

    # BUILDING THE CLASSIFIER
    flow = flow(nn.BatchNorm2d(flow.features))(activation)
    outs = classifier(flow, n_classes, pooling=final_pooling)
    model = FunctionalModel(inputs=inputs, outputs=outs)
    return model


if __name__ == "__main__":
    import torch
    from pytorch_functional import tools
    from logging import basicConfig, DEBUG

    basicConfig(level=DEBUG)

    model = ResNet(
        input_shape=(3, 32, 32),
        n_classes=10,
        version=("WRN", 16, 4),
    )

    input = torch.rand(1, 3, 32, 32)
    outs = model.forward(input)
    print(f"Parameters: {tools.get_parameter_count(model)}")
