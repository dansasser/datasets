import json
import os
import requests


def count_words(text):
    """Count actual words in text"""
    return len(text.split())


def get_quality_score_from_deepseek(text, title, ollama_url):
    """Use DeepSeek via Ollama to score text quality"""
    # Take first 2000 words as sample
    sample = ' '.join(text.split()[:2000])
    
    prompt = f"""Analyze this Christian theological/literary text titled "{title}" and rate its quality on a scale of 1-10 based on:
- Doctrinal soundness and biblical alignment
- Clarity of theological concepts
- Writing quality and readability
- Educational and spiritual value


Text sample:
{sample}


Respond with ONLY a number between 1-10 (can be decimal like 8.5). No explanation, just the number."""


    try:
        response = requests.post(f'{ollama_url}/api/generate', 
            json={
                "model": "deepseek-v3.1:671b-cloud",  # Updated to match your model
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.3,  # Lower temp for more consistent scoring
                    "num_predict": 10    # Only need a short response
                }
            },
            timeout=120  # Cloud model might need more time
        )
        
        if response.status_code == 200:
            score_text = response.json()['response'].strip()
            # Extract just the number (DeepSeek might include some reasoning)
            import re
            numbers = re.findall(r'\d+\.?\d*', score_text)
            if numbers:
                score = float(numbers[0])
                return min(10.0, max(1.0, score))
            else:
                print(f"  Warning: Could not parse score from: {score_text}")
                return 7.0  # Default for Christian content
        else:
            print(f"  Warning: Ollama request failed (status {response.status_code})")
            return 7.0
    except Exception as e:
        print(f"  Warning: DeepSeek error ({e}), using default score")
        return 7.0


# Configure your Ollama cloud server URL
OLLAMA_URL = "http://localhost:11435"  # Correct for your setup


print(f"Using Ollama server at: {OLLAMA_URL}")
print("Processing files...\n")


for json_file in os.listdir('.'):
    if json_file.endswith('.json'):
        txt_file = json_file.replace('.json', '.txt')
        
        if os.path.exists(txt_file):
            try:
                with open(json_file, 'r') as f:
                    metadata = json.load(f)
                
                with open(txt_file, 'r') as f:
                    content = f.read()
                
                # Check if header already exists
                if not content.startswith('Title:'):
                    # Count actual words
                    actual_word_count = count_words(content)
                    word_count = metadata.get('word_count', actual_word_count)
                    
                    # Get quality score
                    if 'quality_score' in metadata and metadata['quality_score'] > 0:
                        quality_score = metadata['quality_score']
                        print(f"Processing {txt_file}...")
                        print(f"  Using existing quality score: {quality_score}")
                    else:
                        print(f"Processing {txt_file}...")
                        print(f"  Generating quality score with DeepSeek...")
                        title = metadata.get('title', 'Unknown')
                        quality_score = get_quality_score_from_deepseek(content, title, OLLAMA_URL)
                        print(f"  Quality score: {quality_score}")
                    
                    header = f"""Title: {metadata.get('title', 'Unknown')}
Author: {metadata.get('author', 'Charles Stanley')}
Source: {metadata.get('source', 'In Touch Ministries')}
Category: {metadata.get('category', 'Sermon')}
Subcategory: {metadata.get('subcategory', 'Unknown')}
Quality Score: {quality_score:.2f}
Biblical Alignment: {metadata.get('biblical_alignment', 0.0):.2f}
Word Count: {word_count:,}
================================================================================


"""
                    with open(txt_file, 'w') as f:
                        f.write(header + content)
                    print(f"✓ Completed\n")
                else:
                    print(f"- Skipped {txt_file} (already has header)")
                    
            except Exception as e:
                print(f"✗ Error processing {json_file}: {e}\n")


print("Done!")
