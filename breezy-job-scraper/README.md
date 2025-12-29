# Breezy ATS Job Scraper

An API-first job scraper for Breezy ATS with comprehensive testing and HTML fallback. Built with production-grade principles prioritizing network interception over DOM scraping.

## Features

- **API-First Approach**: Prioritizes Breezy API calls over HTML scraping
- **Network Interception**: Handles dynamic JS loading correctly
- **Comprehensive Testing**: Full test coverage with pytest
- **Schema-First Extraction**: Structured data models with Pydantic
- **Modular Design**: Reusable and defensive code architecture
- **Error Handling**: Robust error handling and rate limiting
- **Multiple Output Formats**: JSON, CSV support
- **Async Processing**: Concurrent scraping for multiple companies
- **HTML Fallback**: Last-resort HTML scraping when APIs fail
- **Configuration Management**: Environment-based configuration

## Installation

```bash
# Clone the repository
git clone <repository-url>
cd breezy-job-scraper

# Install dependencies
pip install -r requirements.txt

# Copy environment configuration
cp .env.example .env

# Edit .env with your settings
```

## Quick Start

### Command Line Usage

```bash
# Scrape a single company
python -m src.main company-name

# Scrape multiple companies
python -m src.main company1 company2 company3

# Save to specific file
python -m src.main company-name --output results.json

# Use CSV format
python -m src.main company-name --format csv

# Verbose logging
python -m src.main company-name --verbose

# Disable HTML fallback (API only)
python -m src.main company-name --no-html-fallback
```

### Python API Usage

```python
import asyncio
from src import BreezyEnhancedScraper

async def scrape_jobs():
    async with BreezyEnhancedScraper() as scraper:
        result = await scraper.scrape_company_jobs("company-name")
        print(f"Found {result.total_found} positions")
        for position in result.positions:
            print(f"- {position.title} at {position.company.name}")

# Run the scraper
asyncio.run(scrape_jobs())
```

## Architecture

### API-First Strategy

The scraper follows a hierarchical approach:

1. **Breezy API**: Direct API calls to `api.breezy.hr/v3`
2. **Public API**: Public endpoints at `breezy.hr/{slug}/api/positions`
3. **Domain Discovery**: Intelligent company slug discovery
4. **HTML Fallback**: Last resort with BeautifulSoup parsing

### Data Models

- **Position**: Standardized job posting model
- **Company**: Company information model
- **Location**: Structured location data
- **ScrapingResult**: Operation result with metadata

### Error Handling

- Automatic retry with exponential backoff
- Graceful degradation between methods
- Comprehensive error logging
- Rate limiting compliance

## Configuration

### Environment Variables

```bash
# API Configuration
API_TIMEOUT=30
MAX_RETRIES=3
RATE_LIMIT_DELAY=1.0

# Scraping Configuration
MAX_CONCURRENT_REQUESTS=5
ENABLE_HTML_FALLBACK=true
RESPECT_ROBOTS_TXT=true

# Output Configuration
OUTPUT_FORMAT=json
OUTPUT_DIRECTORY=./output
INCLUDE_RAW_DATA=false

# Logging Configuration
LOG_LEVEL=INFO
LOG_FILE=scraper.log
```

### Settings File

Create a `.env` file based on `.env.example`:

```bash
cp .env.example .env
# Edit .env with your preferences
```

## Testing

### Run All Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test file
pytest tests/test_client.py

# Run with verbose output
pytest -v
```

### Test Coverage

- **Models**: Data validation and edge cases
- **Client**: API interactions and error handling
- **Scraper**: HTML parsing and fallback logic
- **Integration**: End-to-end scraping scenarios

## Output Formats

### JSON Output

```json
{
  "scraping_session": {
    "timestamp": "2023-12-01T12:00:00Z",
    "total_companies": 1,
    "successful_companies": 1,
    "total_positions": 5
  },
  "results": [
    {
      "success": true,
      "source": "api",
      "total_found": 5,
      "positions": [...]
    }
  ]
}
```

### CSV Output

Flat CSV format with all job fields including:
- Job details (title, description, type)
- Location information (city, state, country, remote)
- Company information (name, size, industry)
- Salary and requirements
- Scraping metadata

## Advanced Usage

### Custom Configuration

```python
from src import BreezyEnhancedScraper, Settings

# Custom settings
settings = Settings(
    api_timeout=60,
    max_retries=5,
    enable_html_fallback=False,
    output_format="csv"
)

async def custom_scrape():
    async with BreezyEnhancedScraper(timeout=settings.api_timeout) as scraper:
        results = await scraper.scrape_multiple_companies([
            "company1", "company2", "company3"
        ])
        return results
```

### Batch Processing

```python
import asyncio
from src.main import BreezyJobScraperApp

async def batch_scrape():
    app = BreezyJobScraperApp()
    
    companies = ["company1", "company2", "company3"]
    results = await app.scrape_multiple_companies(companies)
    
    # Save results
    output_path = app.save_results(results, "batch_results.json")
    print(f"Results saved to: {output_path}")
    
    # Print summary
    app.print_summary(results)

asyncio.run(batch_scrape())
```

## Error Scenarios

The scraper handles various error scenarios:

- **Network failures**: Automatic retry with backoff
- **API changes**: Graceful fallback to public endpoints
- **Rate limiting**: Configurable delays and concurrent limits
- **Authentication**: Optional token-based authentication
- **Invalid data**: Validation and error reporting

## Production Considerations

- **Rate Limiting**: Respects robots.txt and implements delays
- **User Agents**: Configurable user agent strings
- **Timeouts**: Configurable request timeouts
- **Logging**: Comprehensive logging with file output
- **Monitoring**: Built-in success/failure reporting

## Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit a pull request

## License

This project is licensed under the MIT License.

## Support

For issues and questions:
1. Check the test files for usage examples
2. Review the logging output for debugging
3. Enable verbose logging for detailed information
