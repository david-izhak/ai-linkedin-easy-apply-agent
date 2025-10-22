import pytest
from unittest.mock import AsyncMock
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))

from apply_form.upload_docs import upload_docs
from core.selectors import selectors


class TestUploadDocs:
    
    @pytest.mark.asyncio
    async def test_upload_docs_cv_success(self):
        """Test successful upload of CV."""
        mock_page = AsyncMock()
        mock_div = AsyncMock()
        mock_page.query_selector_all.return_value = [mock_div]
        
        mock_label = AsyncMock()
        mock_input = AsyncMock()
        mock_div.query_selector.side_effect = [mock_label, mock_input]
        mock_label.inner_text.return_value = "Resume"
        
        cv_path = "/path/to/cv.pdf"
        cover_letter_path = ""
        
        await upload_docs(mock_page, cv_path, cover_letter_path)
        
        mock_page.query_selector_all.assert_called_once_with(selectors["document_upload"])
        assert mock_div.query_selector.call_count == 2
        mock_input.set_input_files.assert_called_once_with(cv_path)
    
    @pytest.mark.asyncio
    async def test_upload_docs_cover_letter_success(self):
        """Test successful upload of cover letter."""
        mock_page = AsyncMock()
        mock_div = AsyncMock()
        mock_page.query_selector_all.return_value = [mock_div]
        
        mock_label = AsyncMock()
        mock_input = AsyncMock()
        mock_div.query_selector.side_effect = [mock_label, mock_input]
        mock_label.inner_text.return_value = "Cover Letter"
        
        cv_path = ""
        cover_letter_path = "/path/to/cover_letter.pdf"
        
        await upload_docs(mock_page, cv_path, cover_letter_path)
        
        mock_page.query_selector_all.assert_called_once_with(selectors["document_upload"])
        assert mock_div.query_selector.call_count == 2
        mock_input.set_input_files.assert_called_once_with(cover_letter_path)
    
    @pytest.mark.asyncio
    async def test_upload_docs_both_documents(self):
        """Test upload of both CV and cover letter."""
        mock_page = AsyncMock()
        mock_div1 = AsyncMock()
        mock_div2 = AsyncMock()
        mock_page.query_selector_all.return_value = [mock_div1, mock_div2]
        
        mock_label1 = AsyncMock()
        mock_input1 = AsyncMock()
        mock_label2 = AsyncMock()
        mock_input2 = AsyncMock()
        mock_div1.query_selector.side_effect = [mock_label1, mock_input1]
        mock_div2.query_selector.side_effect = [mock_label2, mock_input2]
        mock_label1.inner_text.return_value = "Resume"
        mock_label2.inner_text.return_value = "Cover Letter"
        
        cv_path = "/path/to/cv.pdf"
        cover_letter_path = "/path/to/cover_letter.pdf"
        
        await upload_docs(mock_page, cv_path, cover_letter_path)
        
        mock_page.query_selector_all.assert_called_once_with(selectors["document_upload"])
        assert mock_div1.query_selector.call_count == 2
        assert mock_div2.query_selector.call_count == 2
        mock_input1.set_input_files.assert_called_once_with(cv_path)
        mock_input2.set_input_files.assert_called_once_with(cover_letter_path)
    
    @pytest.mark.asyncio
    async def test_upload_docs_no_documents(self):
        """Test case when no document paths are provided."""
        mock_page = AsyncMock()
        mock_div = AsyncMock()
        mock_page.query_selector_all.return_value = [mock_div]
        
        mock_label = AsyncMock()
        mock_input = AsyncMock()
        mock_div.query_selector.side_effect = [mock_label, mock_input]
        mock_label.inner_text.return_value = "Resume"
        
        cv_path = ""
        cover_letter_path = ""
        
        await upload_docs(mock_page, cv_path, cover_letter_path)
        
        mock_page.query_selector_all.assert_called_once_with(selectors["document_upload"])
        assert mock_div.query_selector.call_count == 2
        # Should not call set_input_files since paths are empty
        mock_input.set_input_files.assert_not_called()