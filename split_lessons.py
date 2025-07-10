import json
import os

def split_lessons_data(input_filepath="lessons_data.json", output_dir="."):
    """
    Reads the main lessons data file and splits each lesson topic into a separate JSON file.
    Files will be named based on the lesson topic key.
    """
    try:
        with open(input_filepath, 'r', encoding='utf-8') as f:
            lessons_data = json.load(f)
    except FileNotFoundError:
        print(f"Error: Input file '{input_filepath}' not found.")
        return
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from '{input_filepath}'.")
        return
    except Exception as e:
        print(f"An unexpected error occurred while reading '{input_filepath}': {e}")
        return

    if not os.path.exists(output_dir):
        try:
            os.makedirs(output_dir)
            print(f"Created directory: {output_dir}")
        except Exception as e:
            print(f"Error creating output directory '{output_dir}': {e}")
            return

    for topic_key, topic_content in lessons_data.items():
        # Sanitize filename (though current keys are fine, good practice)
        filename_safe_key = "".join(c if c.isalnum() or c in ('.', '_', ' ') else '_' for c in topic_key).strip()
        if not filename_safe_key:
            filename_safe_key = "untitled_lesson"

        output_filename = f"{filename_safe_key}.json"
        output_filepath = os.path.join(output_dir, output_filename)

        try:
            with open(output_filepath, 'w', encoding='utf-8') as outfile:
                json.dump({topic_key: topic_content}, outfile, ensure_ascii=False, indent=2)
            print(f"Successfully created: {output_filepath}")
        except Exception as e:
            print(f"Error writing file '{output_filepath}': {e}")

if __name__ == "__main__":
    # Assuming the script is in interLearn and lessons_data.json is also there.
    # Output files will also be in interLearn.
    split_lessons_data(input_filepath="lessons_data.json", output_dir=".")
    print("Lesson splitting process complete.")