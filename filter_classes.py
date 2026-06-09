import torch

# 모델 로드 (yolov5n.pt 또는 다른 경량 모델)
model = torch.hub.load('ultralytics/yolov5', 'yolov5n', source='local')

# 원하는 클래스 ID만 감지하게 설정 (사람: 0, 자전거: 1, 자동차: 2)
# 참고: COCO 클래스 기준
model.classes = [0, 1, 2]

# 이미지 추론 예시
results = model('your_image.jpg')

# 결과 출력
results.print()
results.show()  # 결과 시각화