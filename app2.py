import sys
from yolov5.export import run  # yolov5 폴더가 같은 경로에 있으므로 가능

def export():
    run(
        weights='yolov5/yolov5n.pt',
        imgsz=(640, 640),
        batch_size=1,
        device='cpu',
        include=['onnx'],
        half=False,
        dynamic=False,
        simplify=True
    )

if __name__ == '__main__':
    export()