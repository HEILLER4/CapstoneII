category_mapping = {'car': 'vehicle', 'bus': 'vehicle', 'motorcycle': 'vehicle', 'truck': 'vehicle',
                    "bicycle": 'vehicle', 'person': 'human', 'dog': 'animal', 'cat': 'animal', 'horse': 'animal',
                    'bottle': 'object', 'cup': 'object', 'book': 'object', 'chair': 'furniture', 'sofa': 'furniture',
                    'bed': 'furniture'}


def get_category(class_name):
    return category_mapping.get(class_name, class_name)
