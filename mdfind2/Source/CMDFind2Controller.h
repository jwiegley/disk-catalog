//
//  CMDFind2Controller.h
//  mdfind2
//
//  Created by Jonathan Wight on 05/26/2005.
//  Copyright (c) 2005 Toxic Software. All rights reserved.
//

#import <Foundation/Foundation.h>

enum {
	MyController_OutputFormatNormal,
	MyController_OutputFormatXML,
	MyController_OutputFormatNullDelimited,
	};

/**
 * @class CMDFind2Controller
 */
@interface CMDFind2Controller : NSObject {
	BOOL runFlag;

	NSMetadataQuery *query;
	int outputFormat;
	int count;
	int limit;
}

- (NSMetadataQuery *)query;

- (void)setOutputFormat:(int)inOutputFormat;

- (void)setLimit:(int)inLimit;

- (void)run;

- (void)processPresearch;
- (void)processItem:(NSMetadataItem *)inItem;
- (void)processPostsearch;

@end
