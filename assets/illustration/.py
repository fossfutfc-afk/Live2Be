from pathlib import Path


def main():
    # 获取当前 Python 脚本所在目录
    script_dir = Path(__file__).resolve().parent
    diff_dir = script_dir / "diff"

    # 检查 diff 文件夹是否存在
    if not diff_dir.exists() or not diff_dir.is_dir():
        print(f"错误：未找到 diff 文件夹！")
        print(f"请确认以下目录是否存在：{diff_dir}")
        return

    # 获取所有 PNG 文件（不区分大小写），去重并排序
    png_files = sorted({
        file.name
        for file in diff_dir.iterdir()
        if file.is_file() and file.suffix.lower() == ".png"
    })

    # 输出结果
    lines = ["emotions:"]

    for filename in png_files:
        lines.append(f"  : diff/{filename}")

    output = "\n".join(lines)

    print(output)

    # 同时保存到文本文件
    output_file = script_dir / "emotions.yml"
    output_file.write_text(output, encoding="utf-8")

    print(f"\n已生成文件：{output_file.name}")


if __name__ == "__main__":
    main()