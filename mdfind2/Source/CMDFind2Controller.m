//
//  CMDFind2Controller.m
//  mdfind2
//
//  Created by Jonathan Wight on 05/26/2005.
//  Copyright (c) 2005 Toxic Software. All rights reserved.
//

#import "CMDFind2Controller.h"

#import "NSMetadataItem_XMLExtensions.h"

@implementation CMDFind2Controller

- (id)init
{
  if ((self = [super init]) != NULL)
    {
      query = [[NSMetadataQuery alloc] init];
      outputFormat = MyController_OutputFormatNormal;
      count = 0;
      limit = 0x7FFFFFFF;

      [[NSNotificationCenter defaultCenter] addObserver:self selector:@selector(metadataQueryDidStartGatheringNotification:) name:NSMetadataQueryDidStartGatheringNotification object:query];
      [[NSNotificationCenter defaultCenter] addObserver:self selector:@selector(metadataQueryDidFinishGatheringNotification:) name:NSMetadataQueryDidFinishGatheringNotification object:query];

      [query addObserver:self forKeyPath:@"results" options:NSKeyValueObservingOptionNew context:NULL];
    }
  return(self);
}

- (void)dealloc
{
  //
  [super dealloc];
}

#pragma mark -

- (NSMetadataQuery *)query
{
  return(query);
}

- (void)setOutputFormat:(int)inOutputFormat
{
  outputFormat = inOutputFormat;
}

- (void)setLimit:(int)inLimit;
{
  limit = inLimit;
}

#pragma mark -

- (void)run
{
  [self processPresearch];

  [query startQuery];

  count = 0;
  runFlag = YES;
  while (runFlag == YES)
    {
      [[NSRunLoop currentRunLoop] runUntilDate:[NSDate dateWithTimeIntervalSinceNow:0.1]];
    }

  [query stopQuery];

  [self processPostsearch];
}

#pragma mark -

- (void)processPresearch
{
  if (outputFormat == MyController_OutputFormatXML)
    {
      NSString *theXMLDeclaration = @"<?xml version=\"1.0\" encoding=\"utf-8\"?>";
      fprintf(stdout, "%s\n", [theXMLDeclaration UTF8String]);

      fprintf(stdout, "<spotlight>\n");

      NSXMLElement *theQueryNode = [NSXMLNode elementWithName:@"query"];
      [theQueryNode addChild:[NSXMLNode textWithStringValue:[[query predicate] description]]];
      fprintf(stdout, "%s\n", [[theQueryNode XMLString] UTF8String]);

      fprintf(stdout, "<results>\n");
    }
}

- (void)processItem:(NSMetadataItem *)inItem
{
  if (outputFormat == MyController_OutputFormatXML)
    {
      NSXMLElement *theElement = [inItem asXMLElement];
      fprintf(stdout, "%s\n", [[theElement XMLString] UTF8String]);
    }
  else
    {
      char theDelimiter = '\n';
      if (outputFormat == MyController_OutputFormatNullDelimited)
	theDelimiter = 0;
      fprintf(stdout, "%s%c", [[inItem valueForAttribute:(NSString *)kMDItemPath] UTF8String], theDelimiter);
    }

}

- (void)processPostsearch
{
  if (outputFormat == MyController_OutputFormatXML)
    {
      fprintf(stdout, "</results>\n");
      fprintf(stdout, "</spotlight>\n");
    }
}

#pragma mark -

- (void)observeValueForKeyPath:(NSString *)keyPath ofObject:(id)object change:(NSDictionary *)change context:(void *)context
{
  NSEnumerator *theEnumerator = [[change objectForKey:NSKeyValueChangeNewKey] objectEnumerator];
  NSMetadataItem *theItem = NULL;
  while ((theItem = [theEnumerator nextObject]) != NULL)
    {
      if (++count > limit)
	{
	  runFlag = NO;
	  break;
	}
      [self processItem:theItem];
    }
}

#pragma mark -

- (void)metadataQueryDidStartGatheringNotification:(NSNotification *)inNotification
{
}

- (void)metadataQueryDidFinishGatheringNotification:(NSNotification *)inNotification
{
  runFlag = NO;
}

@end
