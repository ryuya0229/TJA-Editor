def create_distribution_zip(...):
    # Check if wave_name is None and handle the case appropriately
    if wave_name is None:
        # Handle the None case instead of calling lower()
        pass
    else:
        # Existing logic with wave_name
        wave_name = wave_name.lower()  # This line should be removed
        # Rest of your logic


def generate_dan_code(...):
    processed_set = set()  # Use a processed set for duplicate tracking
    # Existing logic that checks for duplicates
    if some_condition:
        if some_unique_value not in processed_set:
            processed_set.add(some_unique_value)
            # Logic for when the value is unique
        else:
            # Logic for duplicate handling
    # Rest of your logic
