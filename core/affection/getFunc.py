import numpy as np
from scipy.interpolate import BarycentricInterpolator

# 1. 准备数据（示例）
# 请将你的数据替换为真实的 x 和 y 数组
x = np.array([1, 2, 3, ...])  # 你的100个x坐标
y = np.array([15, 30, 45, ...]) # 你的100个y坐标

# 2. 创建插值器
# 这一步只是建立插值规则，不会立即计算所有点
interp = BarycentricInterpolator(x, y)

# 3. 进行插值
# 定义你想要计算插值结果的新x坐标
x_new = np.linspace(min(x), max(x), 500)  # 例如，生成500个密集点用于绘图

# 计算这些新点对应的y值
y_new = interp(x_new)

# 现在 y_new 就是插值结果，你可以用它来绘图或进一步分析